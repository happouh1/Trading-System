"""Offline imports exercise source integrity, ownership, causality, and restart."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_webull_trade_candidate_audit import (
    ENTRY,
    EXIT,
    RECORDED,
    SESSION,
    SHA,
    START,
    _append,
    _fixture,
)

from trading_system.cli.main import main
from trading_system.desktop.dual_source_trade_evidence import TradeEvidenceCandidateRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.webull.trade_evidence import VERSION, parse_capture, utc_text
from trading_system.webull.trade_evidence_registry import (
    TradeEvidenceImportRegistry,
    reconcile_trade_evidence,
)


def evidence_fixture(
    tmp_path: Path,
) -> tuple[SQLiteRepository, dict[str, Any], Path, Path]:
    repository, candidate = _fixture(tmp_path)
    _append(
        repository, "webull_connection_verifications",
        ("verification_id", "session_id", "occurred_at", "account_id_hash"),
        ("verification-fixture", SESSION, utc_text(START), SHA), {"account_id_hash": SHA},
    )
    orders = []
    fills = []
    for role, broker_id, client, side, at, price in (
        ("ENTRY", "broker-1", "entry-client", "BUY", ENTRY, "100.00"),
        ("EXIT", "broker-2", "exit-client", "SELL", EXIT, "102.00"),
    ):
        order = {
            "broker_order_id": broker_id, "client_order_id": client, "account_id_hash": SHA,
            "symbol": "AAPL", "role": role, "side": side, "quantity": 1,
            "filled_quantity": 1, "status": "FILLED", "known_at": utc_text(at),
        }
        orders.append(order)
        fills.append({
            "execution_id": "fill-" + role, "broker_order_id": broker_id,
            "account_id_hash": SHA, "quantity": 1, "price": price, "fee": "0.01",
            "currency": "USD", "executed_at": utc_text(at), "known_at": utc_text(at),
        })
        _append(
            repository, "webull_broker_events",
            ("event_id", "session_id", "client_order_id", "occurred_at", "status"),
            ("event-" + role, SESSION, client, utc_text(at), "FILLED"),
            {key: value for key, value in order.items()
             if key not in {"role", "known_at", "account_id_hash"}},
        )
    positions = [{
        "record_id": "position-" + role, "account_id_hash": SHA, "symbol": "AAPL",
        "role": role, "signed_quantity": 0, "observed_at": utc_text(at),
        "known_at": utc_text(at),
    } for role, at in (("BEFORE", START), ("AFTER", EXIT + timedelta(minutes=1)))]
    source = tmp_path / "retained-redacted-source.json"
    source.write_text(json.dumps({"fixture_only": True, "orders": orders,
                                  "fills": fills, "positions": positions}), encoding="utf-8")
    payload: dict[str, Any] = {
        "schema_version": VERSION, "environment": "SANDBOX", "capture_id": "capture-1",
        "candidate_id": candidate.candidate_id, "account_id_hash": SHA,
        "source_sha256": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        "captured_at": utc_text(RECORDED), "orders": orders, "fills": fills,
        "positions": positions,
    }
    evidence = tmp_path / "normalized-evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    repository.connection.commit()
    return repository, payload, evidence, source


def test_import_restart_permutation_and_read_only_reconciliation(tmp_path: Path) -> None:
    repository, payload, evidence, source = evidence_fixture(tmp_path)
    with repository:
        registry = TradeEvidenceImportRegistry(repository)
        capture, inserted = registry.import_files(
            evidence, source, session_id=SESSION, imported_at=RECORDED,
        )
        assert inserted
        for name in ("orders", "fills", "positions"):
            payload[name].reverse()
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        replay, inserted = registry.import_files(
            evidence, source, session_id=SESSION, imported_at=RECORDED + timedelta(hours=1),
        )
        assert not inserted and capture == replay
        assert repository.connection.execute(
            "SELECT imported_at FROM webull_trade_evidence_imports"
        ).fetchone() == (utc_text(RECORDED),)
        with pytest.raises(ValueError, match="unavailable"):
            registry.load(capture.import_id, as_of=RECORDED - timedelta(microseconds=1))
    with SQLiteRepository(repository.path) as reopened:
        reopened.connection.execute("PRAGMA query_only = ON")
        changes = reopened.connection.total_changes
        report = reconcile_trade_evidence(reopened, capture.import_id, as_of=RECORDED)
        assert report.status == "RECONCILED_PENDING_REVIEW"
        assert report.reason_codes == ()
        assert report.incremental_fill_count == 2
        assert str(report.total_reported_fees) == "0.02"
        assert not report.qualifying_completed_trade
        assert not report.source_authenticity_verified
        assert not report.network_used and not report.broker_write_performed
        assert reopened.connection.total_changes == changes
        assert report == reconcile_trade_evidence(reopened, capture.import_id, as_of=RECORDED)


@pytest.mark.parametrize(("section", "field", "value", "reason"), [
    ("fills", "quantity", 2, "ORDER_FILL_QUANTITY_MISMATCH"),
    ("fills", "price", "101.00", "ENTRY_PRICE_MISMATCH"),
    ("orders", "side", "SELL", "ORDER_SYMBOL_OR_SIDE_MISMATCH"),
    ("positions", "signed_quantity", 1, "NONFLAT_ACCOUNT_BASELINE_OR_CLOSE"),
    ("positions", "symbol", "MSFT", "POSITION_SYMBOL_MISMATCH"),
])
def test_reconciliation_rejects_disagreements(
    tmp_path: Path, section: str, field: str, value: object, reason: str,
) -> None:
    repository, payload, evidence, source = evidence_fixture(tmp_path)
    payload[section][0][field] = value
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with repository:
        capture, _ = TradeEvidenceImportRegistry(repository).import_files(
            evidence, source, session_id=SESSION, imported_at=RECORDED,
        )
        report = reconcile_trade_evidence(repository, capture.import_id, as_of=RECORDED)
        assert reason in report.reason_codes
        assert report.status == "MISMATCH"
        assert not report.qualifying_completed_trade


@pytest.mark.parametrize(("section", "field", "value"), [
    ("orders", "account_id_hash", "sha256:" + "b" * 64),
    ("orders", "quantity", True),
    ("orders", "status", "OPEN"),
    ("fills", "quantity", 1.5),
    ("fills", "price", "NaN"),
    ("fills", "fee", -1),
    ("fills", "currency", "EUR"),
    ("fills", "executed_at", "2026-10-12T14:30:00"),
    ("fills", "known_at", "2026-10-13T14:30:00Z"),
    ("positions", "role", "UNKNOWN"),
])
def test_invalid_contracts_are_rejected_before_import(
    tmp_path: Path, section: str, field: str, value: object,
) -> None:
    repository, payload, evidence, source = evidence_fixture(tmp_path)
    payload[section][0][field] = value
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with repository:
        with pytest.raises(ValueError):
            TradeEvidenceImportRegistry(repository).import_files(
                evidence, source, session_id=SESSION, imported_at=RECORDED,
            )
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_trade_evidence_imports"
        ).fetchone() == (0,)


def test_source_integrity_duplicate_keys_and_unknown_fields(tmp_path: Path) -> None:
    repository, payload, evidence, source = evidence_fixture(tmp_path)
    with repository:
        source.write_text("changed", encoding="utf-8")
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            TradeEvidenceImportRegistry(repository).import_files(
                evidence, source, session_id=SESSION, imported_at=RECORDED,
            )
        with pytest.raises(ValueError, match="duplicate"):
            parse_capture('{"capture_id":"one","capture_id":"two"}')
        payload["app_secret"] = "must-not-be-imported"
        with pytest.raises(ValueError, match="fields"):
            parse_capture(json.dumps(payload))
        del payload["app_secret"]
        payload["fills"].append(payload["fills"][0])
        with pytest.raises(ValueError, match="duplicate"):
            parse_capture(json.dumps(payload))


def test_cross_candidate_reuse_rolls_back_all_claims_and_import(tmp_path: Path) -> None:
    repository, payload, evidence, source = evidence_fixture(tmp_path)
    with repository:
        registry = TradeEvidenceImportRegistry(repository)
        registry.import_files(evidence, source, session_id=SESSION, imported_at=RECORDED)
        candidate = TradeEvidenceCandidateRegistry(repository).get(payload["candidate_id"])
        other = replace(candidate, source_trade_id="different-managed-position")
        TradeEvidenceCandidateRegistry(repository).insert(other)
        payload["candidate_id"] = other.candidate_id
        payload["capture_id"] = "different-capture"
        payload["orders"].append({**payload["orders"][1], "broker_order_id": "unused-order",
                                  "client_order_id": "aaa-new", "status": "CANCELLED",
                                  "filled_quantity": 0})
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        before = repository.connection.execute(
            "SELECT * FROM webull_trade_evidence_claims ORDER BY record_kind, record_id"
        ).fetchall()
        with pytest.raises(ValueError, match="reused or revised"):
            registry.import_files(evidence, source, session_id=SESSION, imported_at=RECORDED)
        assert repository.connection.execute(
            "SELECT * FROM webull_trade_evidence_claims ORDER BY record_kind, record_id"
        ).fetchall() == before
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_trade_evidence_imports"
        ).fetchone() == (1,)


def test_revisions_immutability_and_session_scope(tmp_path: Path) -> None:
    repository, payload, evidence, source = evidence_fixture(tmp_path)
    with repository:
        registry = TradeEvidenceImportRegistry(repository)
        with pytest.raises(ValueError, match="selected session"):
            registry.import_files(evidence, source, session_id="other", imported_at=RECORDED)
        with pytest.raises(ValueError, match="causal"):
            registry.import_files(
                evidence, source, session_id=SESSION, imported_at=RECORDED - timedelta(seconds=1),
            )
        registry.import_files(evidence, source, session_id=SESSION, imported_at=RECORDED)
        payload["fills"][0]["fee"] = "0.02"
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="conflicting"):
            registry.import_files(evidence, source, session_id=SESSION, imported_at=RECORDED)
        payload["capture_id"] = "revision-2"
        evidence.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="reused or revised"):
            registry.import_files(evidence, source, session_id=SESSION, imported_at=RECORDED)
        for table in ("webull_trade_evidence_imports", "webull_trade_evidence_claims"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                repository.connection.execute(f"DELETE FROM {table}")


def test_cli_reconciles_without_credentials_or_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, _, evidence, source = evidence_fixture(tmp_path)
    with repository:
        capture, _ = TradeEvidenceImportRegistry(repository).import_files(
            evidence, source, session_id=SESSION, imported_at=RECORDED,
        )

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline evidence must not contact network or load credentials")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("trading_system.webull.cli.load_credentials", forbidden)
    args = ["webull", "reconcile-trade-evidence", "--database", str(repository.path),
            "--config", "config/webull.sandbox.v1.yaml", "--import-id", capture.import_id,
            "--as-of", utc_text(RECORDED)]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "RECONCILED_PENDING_REVIEW"
    assert result["qualifying_completed_trade"] is False
    args[-1] = utc_text(RECORDED - timedelta(seconds=1))
    assert main(args) == 1
    assert "unavailable" in capsys.readouterr().err


def test_webull_candidate_rejects_any_simulation_hash(tmp_path: Path) -> None:
    repository, candidate = _fixture(tmp_path)
    with repository, pytest.raises(ValueError, match="candidate"):
        replace(candidate, simulation_model_hash="invalid-hash")
