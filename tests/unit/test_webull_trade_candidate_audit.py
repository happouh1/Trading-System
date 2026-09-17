"""Read-only local Webull candidate consistency checks; no trade qualification."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop.dual_source_trade_evidence import (
    TradeEvidenceCandidate,
    TradeEvidenceCandidateRegistry,
)
from trading_system.desktop.webull_trade_candidate_audit import audit_webull_trade_candidate
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

START = datetime(2026, 10, 12, 13, 30, tzinfo=UTC)
ENTRY = START + timedelta(hours=1)
EXIT = START + timedelta(hours=2)
RECORDED = START + timedelta(hours=3)
SHA = "sha256:" + "a" * 64
PLAN = "future-approved-plan-fixture"
SESSION = "broker-audit-session"
POSITION = "managed-1"


def _time(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _append(
    repository: SQLiteRepository,
    table: str,
    columns: tuple[str, ...],
    values: tuple[object, ...],
    payload: object,
) -> str:
    payload_hash = canonical_hash(payload)
    names = (*columns, "payload_json", "payload_hash")
    repository.connection.execute(
        f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
        (*values, canonical_json(payload), payload_hash),
    )
    return payload_hash


def _fixture(tmp_path: Path) -> tuple[SQLiteRepository, TradeEvidenceCandidate]:
    repository = SQLiteRepository(tmp_path / "broker-audit.sqlite")
    repository.migrate()
    PaperRegistry(repository).insert_session(
        PaperSession(SESSION, START, PaperMode.SHADOW, "git:test", SHA,
                     "fixture", "exchange-calendars-4")
    )
    _append(
        repository,
        "paper_burn_in_session_bindings",
        ("binding_id", "session_id", "plan_id", "baseline_session_id",
         "runtime_lock_hash", "started_at", "code_version", "config_hash",
         "data_revision", "calendar_version"),
        ("binding-1", SESSION, PLAN, "baseline-1", SHA, _time(START),
         "git:test", SHA, "fixture", "exchange-calendars-4"),
        {"binding": "binding-1"},
    )
    _append(
        repository,
        "paper_intents",
        ("intent_id", "session_id", "trade_plan_id", "scheduled_open", "status"),
        ("intent-1", SESSION, "trade-plan-1", _time(ENTRY), "SHADOWED"),
        {"payload": {"source_decision_id": "decision-1"}},
    )
    _append(
        repository,
        "webull_managed_positions",
        ("managed_position_id", "session_id", "entry_intent_id",
         "entry_client_order_id", "entry_broker_order_id", "symbol", "direction",
         "filled_quantity", "remaining_quantity", "entry_price", "initial_stop_adjusted",
         "opened_at", "config_hash", "code_version"),
        (POSITION, SESSION, "intent-1", "entry-client", "broker-1", "AAPL", "LONG",
         1, 1, "100", "95", _time(ENTRY), SHA, "git:test"),
        {"managed_position": POSITION},
    )
    _append(
        repository,
        "webull_executions",
        ("execution_id", "session_id", "client_order_id", "occurred_at",
         "symbol", "side", "cumulative_quantity"),
        ("entry-execution", SESSION, "entry-client", _time(ENTRY), "AAPL", "BUY", 1),
        {"execution": "entry"},
    )
    _append(
        repository,
        "webull_broker_action_events",
        ("broker_action_id", "managed_position_id", "session_id", "action_kind",
         "event_type", "client_order_id", "request_hash", "occurred_at"),
        ("exit-action", POSITION, SESSION, "PLACE_EXIT", "ACKNOWLEDGED",
         "exit-client", SHA, _time(EXIT)),
        {"action": "exit"},
    )
    _append(
        repository,
        "webull_executions",
        ("execution_id", "session_id", "client_order_id", "occurred_at",
         "symbol", "side", "cumulative_quantity"),
        ("exit-execution", SESSION, "exit-client", _time(EXIT), "AAPL", "SELL", 1),
        {"execution": "exit"},
    )
    terminal_hash = _append(
        repository,
        "webull_position_events",
        ("position_event_id", "managed_position_id", "session_id", "occurred_at",
         "state", "remaining_quantity", "reason", "evidence_hash"),
        ("terminal-1", POSITION, SESSION, _time(EXIT), "FLAT", 0, "MAX_HOLD", SHA),
        {"terminal": POSITION},
    )
    _append(
        repository,
        "webull_position_reconciliations",
        ("reconciliation_id", "managed_position_id", "session_id", "occurred_at",
         "expected_quantity", "actual_quantity", "matched"),
        ("reconciliation-1", POSITION, SESSION, _time(EXIT + timedelta(minutes=1)), 0, 0, 1),
        {"reconciliation": POSITION},
    )
    candidate = TradeEvidenceCandidate(
        PLAN, SESSION, "decision-1", "WEBULL_SANDBOX", POSITION,
        ENTRY, EXIT, RECORDED, terminal_hash, SHA, "git:test",
    )
    assert TradeEvidenceCandidateRegistry(repository).insert(candidate)
    repository.connection.commit()
    return repository, candidate


def test_complete_local_chain_is_consistent_but_not_qualified(tmp_path: Path) -> None:
    repository, candidate = _fixture(tmp_path)
    with repository:
        changes_before = repository.connection.total_changes
        first = audit_webull_trade_candidate(repository, candidate, as_of=RECORDED)
        second = audit_webull_trade_candidate(repository, candidate, as_of=RECORDED)
        assert repository.connection.total_changes == changes_before
        assert first == second
        assert first.locally_consistent
        assert not first.reason_codes
        assert first.evidence_hashes
        assert not first.qualifying_completed_trade
        assert not first.network_used
        assert not first.broker_write_performed


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DELETE FROM webull_executions WHERE execution_id = 'exit-execution'",
         "EXIT_QUANTITY_UNPROVEN"),
        ("UPDATE webull_position_reconciliations SET actual_quantity = 1",
         "FLAT_RECONCILIATION_MISMATCH"),
        ("UPDATE paper_intents SET payload_json = '{}'", "INVALID_STORED_PAYLOAD"),
        ("UPDATE webull_position_events SET remaining_quantity = 1",
         "TERMINAL_POSITION_MISMATCH"),
        ("UPDATE webull_executions SET side = 'BUY' WHERE execution_id = 'exit-execution'",
         "EXIT_EXECUTION_MISMATCH"),
        ("UPDATE webull_executions SET occurred_at = '2026-10-12T15:00:00.000000Z' "
         "WHERE execution_id = 'entry-execution'", "ENTRY_EXECUTION_MISMATCH"),
        ("UPDATE webull_broker_action_events SET occurred_at = '2026-10-12T16:00:00.000000Z'",
         "EXIT_ACTION_AFTER_CLOSE"),
        ("UPDATE burn_in_trade_evidence_candidates SET decision_id = 'different-decision'",
         "CANDIDATE_NOT_REGISTERED"),
    ],
)
def test_missing_or_tampered_local_evidence_fails_closed(
    tmp_path: Path, sql: str, reason: str
) -> None:
    repository, candidate = _fixture(tmp_path)
    with repository:
        repository.connection.execute(sql)
        report = audit_webull_trade_candidate(repository, candidate, as_of=RECORDED)
        assert not report.locally_consistent
        assert reason in report.reason_codes
        assert not report.qualifying_completed_trade


def test_wrong_source_unregistered_and_future_cutoff_fail(tmp_path: Path) -> None:
    repository, candidate = _fixture(tmp_path)
    with repository:
        with pytest.raises(ValueError, match="broker candidate"):
            audit_webull_trade_candidate(
                repository,
                replace(candidate, source="SHADOW_SIMULATED", simulation_model_hash=SHA),
                as_of=RECORDED,
            )
        with pytest.raises(ValueError, match="causal UTC cutoff"):
            audit_webull_trade_candidate(repository, candidate, as_of=EXIT)
        unregistered = replace(candidate, source_trade_id="other-managed-position")
        report = audit_webull_trade_candidate(repository, unregistered, as_of=RECORDED)
        assert "CANDIDATE_NOT_REGISTERED" in report.reason_codes
        assert not report.qualifying_completed_trade
