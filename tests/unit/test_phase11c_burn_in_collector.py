from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.desktop.burn_in_collector import (
    BurnInCollectionResult,
    BurnInCollectorConfigError,
    collect_burn_in_observation,
    load_burn_in_collector_config,
    load_burn_in_collector_plan,
)
from trading_system.desktop.prospective_burn_in import ProspectiveBurnInPlan
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase11c.v1.yaml"
HASH = "sha256:" + "a" * 64
OBSERVED = datetime(2026, 9, 14, 20, tzinfo=UTC)


def _plan() -> ProspectiveBurnInPlan:
    return ProspectiveBurnInPlan(
        "plan-1",
        datetime(2026, 9, 12, tzinfo=UTC),
        datetime(2026, 9, 14, 13, 30, tzinfo=UTC),
        datetime(2026, 10, 9, 20, tzinfo=UTC),
        10,
        20,
        10,
        ("BEARISH", "BULLISH", "RANGE"),
        ("AAPL", "MSFT", "SPY"),
        ("1H", "DAILY"),
        ("BREAKOUT", "RECLAIM"),
        0,
        0,
        0,
        Decimal("0.10"),
        0,
        "release-1",
        HASH,
        HASH,
    )


def _config(tmp_path: Path) -> Path:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["evidence_output"] = "observations.json"
    raw["runtime_lock"] = "runtime-lock.json"
    (tmp_path / "runtime-lock.json").write_text(
        json.dumps(_runtime_lock()),
        encoding="utf-8",
    )
    path = tmp_path / "collector.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _runtime_lock() -> dict[str, object]:
    return {
        "runtime_lock_version": "11E.1.0",
        "mode": "CONTINUITY_LOCK_FROM_INITIAL_SESSION",
        "plan_id": "plan-1",
        "baseline": {
            "session_id": "burn-1",
            "code_version": "test",
            "config_hash": HASH,
            "data_revision": "fixture",
            "calendar_version": "exchange-calendars-4",
        },
        "retrospective_baseline_disclosed": True,
        "authority": {
            "database_read_enabled": True,
            "database_write_enabled": False,
            "network_enabled": False,
            "credential_loading_enabled": False,
            "broker_writes_enabled": False,
            "sandbox_execution_enabled": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
        },
    }


def _insert(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    values: tuple[object, ...],
    payload: object,
) -> None:
    names = (*columns, "payload_json", "payload_hash")
    connection.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
        (*values, canonical_json(payload), canonical_hash(payload)),
    )


def _database(
    path: Path,
    *,
    verified: bool = True,
    operational_evidence: bool = True,
    metrics: bool = False,
) -> None:
    with SQLiteRepository(path) as repository:
        repository.migrate()
        connection = repository.connection
        payload = {"session_id": "burn-1", "mode": "SHADOW"}
        _insert(
            connection,
            "paper_sessions",
            (
                "session_id",
                "created_at",
                "mode",
                "code_version",
                "config_hash",
                "data_revision",
                "calendar_version",
            ),
            (
                "burn-1",
                "2026-09-14T13:30:00.000000Z",
                "SHADOW",
                "test",
                HASH,
                "fixture",
                "exchange-calendars-4",
            ),
            payload,
        )
        if verified:
            _insert(
                connection,
                "webull_connection_verifications",
                ("verification_id", "session_id", "occurred_at", "account_id_hash"),
                ("verify-1", "burn-1", "2026-09-14T14:00:00.000000Z", HASH),
                {"verification_id": "verify-1", "environment": "SANDBOX"},
            )
        if operational_evidence:
            _insert(
                connection,
                "paper_heartbeats",
                ("heartbeat_id", "session_id", "occurred_at", "state"),
                (
                    "heartbeat-1",
                    "burn-1",
                    "2026-09-14T19:59:00.000000Z",
                    "SHADOW",
                ),
                {"heartbeat_id": "heartbeat-1", "state": "SHADOW"},
            )
        if metrics:
            _metric_rows(connection)
        connection.commit()


def _metric_rows(connection: sqlite3.Connection) -> None:
    intent_payload = {"intent_id": "intent-1"}
    _insert(
        connection,
        "paper_intents",
        ("intent_id", "session_id", "trade_plan_id", "scheduled_open", "status"),
        (
            "intent-1",
            "burn-1",
            "plan-trade-1",
            "2026-09-14T14:30:00.000000Z",
            "RECORDED",
        ),
        intent_payload,
    )
    for identity, client, event_type in (
        ("submit-1", "client-1", "CALL_STARTED"),
        ("submit-2", "client-1", "REJECTED"),
        ("submit-3", "client-2", "AMBIGUOUS"),
    ):
        _insert(
            connection,
            "webull_submission_events",
            (
                "submission_event_id",
                "session_id",
                "intent_id",
                "client_order_id",
                "request_hash",
                "occurred_at",
                "event_type",
            ),
            (
                identity,
                "burn-1",
                "intent-1",
                client,
                HASH,
                "2026-09-14T15:00:00.000000Z",
                event_type,
            ),
            {"event": identity},
        )
    _insert(
        connection,
        "paper_incidents",
        ("incident_id", "session_id", "occurred_at", "reason"),
        ("incident-1", "burn-1", "2026-09-14T16:00:00.000000Z", "STALE_COMPLETED_BAR"),
        {"incident_id": "incident-1"},
    )
    _insert(
        connection,
        "paper_reconciliations",
        ("reconciliation_id", "session_id", "occurred_at", "matched"),
        ("reconcile-1", "burn-1", "2026-09-14T17:00:00.000000Z", 0),
        {"reconciliation_id": "reconcile-1"},
    )
    position_payload = {"managed_position_id": "position-1"}
    _insert(
        connection,
        "webull_managed_positions",
        (
            "managed_position_id",
            "session_id",
            "entry_intent_id",
            "entry_client_order_id",
            "entry_broker_order_id",
            "symbol",
            "direction",
            "filled_quantity",
            "remaining_quantity",
            "entry_price",
            "initial_stop_adjusted",
            "opened_at",
            "config_hash",
            "code_version",
        ),
        (
            "position-1",
            "burn-1",
            "intent-1",
            "client-1",
            "broker-1",
            "AAPL",
            "LONG",
            1,
            0,
            "100",
            "95",
            "2026-09-14T15:30:00.000000Z",
            HASH,
            "test",
        ),
        position_payload,
    )
    _insert(
        connection,
        "webull_position_events",
        (
            "position_event_id",
            "managed_position_id",
            "session_id",
            "occurred_at",
            "state",
            "remaining_quantity",
            "reason",
            "evidence_hash",
        ),
        (
            "position-event-1",
            "position-1",
            "burn-1",
            "2026-09-14T19:00:00.000000Z",
            "FLAT",
            0,
            "EXIT_FILLED",
            HASH,
        ),
        {"position_event_id": "position-event-1"},
    )


def _collect(
    tmp_path: Path,
    database: Path,
    *,
    observed_at: datetime = OBSERVED,
    regime: str = "BULLISH",
    symbols: tuple[str, ...] = ("AAPL",),
    timeframes: tuple[str, ...] = ("1H",),
    strategy_categories: tuple[str, ...] = ("BREAKOUT",),
) -> BurnInCollectionResult:
    return collect_burn_in_observation(
        load_burn_in_collector_config(_config(tmp_path)),
        _plan(),
        project_root=tmp_path,
        database=database,
        session_id="burn-1",
        market_day=date(2026, 9, 14),
        observed_at=observed_at,
        regime=regime,
        symbols=symbols,
        timeframes=timeframes,
        strategy_categories=strategy_categories,
    )


def test_config_rejects_network_and_escaping_output(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BurnInCollectorConfigError, match="unsafe"):
        load_burn_in_collector_config(path)
    raw["authority"]["network_enabled"] = False
    raw["evidence_output"] = "../outside.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BurnInCollectorConfigError, match="unsafe"):
        load_burn_in_collector_config(path)


def test_saved_plan_identity_is_loaded_without_reconstruction(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["plan"] = "plan.json"
    config_path = tmp_path / "collector.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    (tmp_path / "plan.json").write_text(canonical_json(_plan()), encoding="utf-8")
    config = load_burn_in_collector_config(config_path)
    plan = load_burn_in_collector_plan(config, project_root=tmp_path)
    assert plan.plan_id == "plan-1"
    assert plan.window_start == datetime(2026, 9, 14, 13, 30, tzinfo=UTC)


def test_collects_metrics_atomically_and_is_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database, metrics=True)
    first = _collect(tmp_path, database)
    second = _collect(tmp_path, database)
    assert first.inserted
    assert not second.inserted
    assert first.local_evidence_write_performed
    assert not second.local_evidence_write_performed
    assert first.observation == second.observation
    assert first.observation.completed_trades == 1
    assert first.observation.order_attempts == 1
    assert first.observation.rejected_orders == 1
    assert first.observation.incidents == 1
    assert first.observation.unmatched_reconciliations == 1
    assert first.observation.stale_data_events == 1
    assert first.observation.unresolved_recoveries == 1
    assert first.source_row_count > 1
    assert first.runtime_validation_id.startswith("burn_in_runtime_validation_")
    assert first.runtime_lock_hash.startswith("sha256:")
    assert not first.network_used
    assert not first.broker_write_performed


def test_rejects_preclose_missing_verification_and_unplanned_classification(
    tmp_path: Path,
) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database, verified=False)
    with pytest.raises(ValueError, match="completed XNYS"):
        _collect(
            tmp_path,
            database,
            observed_at=datetime(2026, 9, 14, 19, 59, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="verification"):
        _collect(tmp_path, database)
    with pytest.raises(ValueError, match="outside the preregistered"):
        _collect(tmp_path, database, symbols=("NVDA",))


def test_conflicting_same_session_recollection_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database)
    _collect(tmp_path, database)
    with pytest.raises(ValueError, match="conflicting evidence"):
        _collect(tmp_path, database, regime="RANGE")


def test_rejects_session_without_operational_evidence(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database, operational_evidence=False)
    with pytest.raises(ValueError, match="no causal operational evidence"):
        _collect(tmp_path, database)


def test_rejects_runtime_identity_drift(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE paper_sessions SET code_version='changed' WHERE session_id='burn-1'"
        )
    with pytest.raises(ValueError, match="runtime drift: code_version"):
        _collect(tmp_path, database)


def test_result_contract_rejects_authority(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database)
    result = _collect(tmp_path, database)
    with pytest.raises(ValueError, match="collection result"):
        replace(result, broker_write_performed=True)


def test_cli_collects_without_network_or_broker_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "paper.sqlite"
    _database(database)
    directory = ROOT / f".tmp-phase11c-{canonical_hash(str(tmp_path)).split(':', 1)[1]}"
    output = directory / "observations.json"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["evidence_output"] = output.relative_to(ROOT).as_posix()
    plan_path = directory / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(canonical_json(_plan()), encoding="utf-8")
    raw["plan"] = plan_path.relative_to(ROOT).as_posix()
    runtime_lock = directory / "runtime-lock.json"
    runtime_lock.write_text(json.dumps(_runtime_lock()), encoding="utf-8")
    raw["runtime_lock"] = runtime_lock.relative_to(ROOT).as_posix()
    collector_config = tmp_path / "collector.json"
    collector_config.write_text(json.dumps(raw), encoding="utf-8")
    try:
        assert main(
            [
                "desktop",
                "burn-in-collect",
                "--config",
                str(collector_config),
                "--database",
                str(database),
                "--session-id",
                "burn-1",
                "--market-day",
                "2026-09-14",
                "--observed-at",
                "2026-09-14T20:00:00Z",
                "--regime",
                "BULLISH",
                "--symbols",
                "AAPL",
                "--timeframes",
                "1H",
                "--strategies",
                "BREAKOUT",
                "--project-root",
                str(ROOT),
            ]
        ) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["inserted"] is True
        assert result["network_used"] is False
        assert result["broker_write_performed"] is False
        assert output.is_file()
    finally:
        shutil.rmtree(directory, ignore_errors=True)
