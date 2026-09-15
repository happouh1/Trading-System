from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.desktop.burn_in_runtime_lock import (
    BurnInRuntimeLockConfigError,
    load_burn_in_runtime_lock,
    validate_burn_in_runtime,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase11e.v1.yaml"
NOW = datetime(2026, 9, 14, 20, tzinfo=UTC)


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """CREATE TABLE paper_sessions(
             session_id TEXT PRIMARY KEY,created_at TEXT,code_version TEXT,
             config_hash TEXT,data_revision TEXT,calendar_version TEXT)"""
    )
    connection.execute(
        "INSERT INTO paper_sessions VALUES(?,?,?,?,?,?)",
        (
            "burn-in-20260914-01",
            "2026-09-14T13:42:00.607341Z",
            "0.2.0",
            "sha256:e707870227ebeb06c60dd94d6283dc8a63160685ebb15447b0dbf89480f8ff7c",
            "WEBULL_SANDBOX_BURNIN_20260914",
            "exchange-calendars-4",
        ),
    )
    return connection


def test_runtime_lock_matches_persisted_initial_session() -> None:
    lock = load_burn_in_runtime_lock(CONFIG)
    with _connection() as connection:
        result = validate_burn_in_runtime(
            connection,
            lock,
            session_id="burn-in-20260914-01",
            plan_id=lock.plan_id,
            validated_at=NOW,
        )
    assert result.matched
    assert result.mismatch_fields == ()
    assert result.read_only
    assert not result.database_write_performed
    assert not result.broker_write_performed


def test_runtime_drift_is_explicit_and_deterministic() -> None:
    lock = load_burn_in_runtime_lock(CONFIG)
    with _connection() as connection:
        connection.execute(
            "UPDATE paper_sessions SET data_revision='OTHER',calendar_version='OTHER'"
        )
        first = validate_burn_in_runtime(
            connection,
            lock,
            session_id="burn-in-20260914-01",
            plan_id=lock.plan_id,
            validated_at=NOW,
        )
        second = validate_burn_in_runtime(
            connection,
            lock,
            session_id="burn-in-20260914-01",
            plan_id=lock.plan_id,
            validated_at=NOW,
        )
    assert first == second
    assert not first.matched
    assert first.mismatch_fields == ("calendar_version", "data_revision")


def test_lock_rejects_unsafe_authority_and_false_disclosure(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BurnInRuntimeLockConfigError, match="unsafe"):
        load_burn_in_runtime_lock(path)
    raw["authority"]["broker_writes_enabled"] = False
    raw["retrospective_baseline_disclosed"] = False
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BurnInRuntimeLockConfigError, match="unsafe"):
        load_burn_in_runtime_lock(path)


def test_validation_rejects_wrong_plan_future_session_and_authority() -> None:
    lock = load_burn_in_runtime_lock(CONFIG)
    with _connection() as connection:
        with pytest.raises(ValueError, match="different plan"):
            validate_burn_in_runtime(
                connection,
                lock,
                session_id="burn-in-20260914-01",
                plan_id="other-plan",
                validated_at=NOW,
            )
        with pytest.raises(ValueError, match="future-known"):
            validate_burn_in_runtime(
                connection,
                lock,
                session_id="burn-in-20260914-01",
                plan_id=lock.plan_id,
                validated_at=datetime(2026, 9, 14, 13, tzinfo=UTC),
            )
        result = validate_burn_in_runtime(
            connection,
            lock,
            session_id="burn-in-20260914-01",
            plan_id=lock.plan_id,
            validated_at=NOW,
        )
    with pytest.raises(ValueError, match="runtime validation"):
        replace(result, network_used=True)
