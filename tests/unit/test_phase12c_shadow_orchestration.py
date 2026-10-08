from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.paper import RuntimeState
from trading_system.paper.prospective_shadow_orchestrator import (
    ProspectiveShadowScheduleConfigError,
    complete_scheduled_shadow_day,
    inspect_scheduled_shadow_target,
    load_prospective_shadow_schedule,
    start_scheduled_shadow_day,
)
from trading_system.persistence import RunRecord, SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull.contracts import AccountVerification
from trading_system.webull.registry import WebullRegistry

ROOT = Path(__file__).parents[2]
START = datetime(2026, 10, 7, 13, 30, tzinfo=UTC)
CLOSE = datetime(2026, 10, 7, 20, 5, tzinfo=UTC)


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12c.schedule.v1.json",
        "config/burn-in.phase12c.launch.v1.json",
        "config/burn-in.phase12c.plan.v1.json",
        "config/desktop.phase12c.runtime-lock.v1.json",
        "config/paper.phase3b.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/webull.phase12c.readonly.v1.json",
        "config/webull.phase12c.decisions.v1.json",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def test_checked_in_schedule_is_exact_safe_and_dst_aware() -> None:
    config = load_prospective_shadow_schedule(
        ROOT / "config/burn-in.phase12c.schedule.v1.json"
    )
    assert len(config.sessions) == 20
    assert config.sessions[0].market_day.isoformat() == "2026-10-07"
    assert config.sessions[-1].market_day.isoformat() == "2026-11-03"
    assert config.sessions[0].open_at.hour == 13
    assert config.sessions[-1].open_at.hour == 14
    assert config.sessions[-1].close_at.hour == 21

    target = inspect_scheduled_shadow_target(config, as_of=START, action="START")
    assert target["eligible"] is True
    assert target["session_id"] == "burn-in-shadow-20261007-01"
    closed = inspect_scheduled_shadow_target(
        config,
        as_of=datetime(2026, 10, 10, 13, 30, tzinfo=UTC),
        action="START",
    )
    assert closed["eligible"] is False
    assert closed["reason"] == "NOT_A_FROZEN_XNYS_SESSION"


def test_scheduled_start_is_idempotent_and_shadow_only(tmp_path: Path) -> None:
    root = _project(tmp_path)
    config = load_prospective_shadow_schedule(
        root / "config/burn-in.phase12c.schedule.v1.json"
    )
    first = start_scheduled_shadow_day(
        config,
        schedule_path="config/burn-in.phase12c.schedule.v1.json",
        project_root=root,
        as_of=START,
    )
    second = start_scheduled_shadow_day(
        config,
        schedule_path="config/burn-in.phase12c.schedule.v1.json",
        project_root=root,
        as_of=START,
    )
    assert first["receipt_id"] == second["receipt_id"]
    assert first["broker_write_performed"] is False
    with SQLiteRepository(root / "webull-sandbox.sqlite") as repository:
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM paper_shadow_orchestration_receipts"
        ).fetchone() == (1,)
        assert repository.connection.execute(
            "SELECT new_state FROM paper_transitions ORDER BY rowid DESC LIMIT 1"
        ).fetchone() == (RuntimeState.SHADOW.value,)


def test_completion_requires_and_seals_read_only_cycles(tmp_path: Path) -> None:
    root = _project(tmp_path)
    config = load_prospective_shadow_schedule(
        root / "config/burn-in.phase12c.schedule.v1.json"
    )
    start_scheduled_shadow_day(
        config,
        schedule_path="config/burn-in.phase12c.schedule.v1.json",
        project_root=root,
        as_of=START,
    )
    with pytest.raises(ValueError, match="verification and network-read data"):
        complete_scheduled_shadow_day(config, project_root=root, as_of=CLOSE)

    database = root / "webull-sandbox.sqlite"
    session_id = "burn-in-shadow-20261007-01"
    worker_payload = {
        "cycle_id": "worker-cycle",
        "broker_write_performed": False,
        "order_api_available": False,
    }
    decision_payload = {
        "cycle_id": "decision-cycle",
        "broker_write_performed": False,
        "simulated_fills_enabled": False,
    }
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(
            RunRecord(
                "decision-run",
                datetime(2026, 10, 7, 20, 5, tzinfo=UTC),
                "0.2.0",
                "sha256:" + "c" * 64,
                "PHASE12C-TEST",
                "exchange-calendars-4",
                20261007,
            )
        )
        WebullRegistry(repository).insert_verification(
            AccountVerification(
                "verification-12c",
                session_id,
                    datetime(2026, 10, 7, 13, 31, tzinfo=UTC),
                "sha256:" + "a" * 64,
                1,
            )
        )
        repository.connection.execute(
            """INSERT INTO webull_burn_in_worker_cycles
               (cycle_id,session_id,observed_at,config_hash,history_responses,
                completed_bars_seen,new_bars_persisted,heartbeat_inserted,network_used,
                payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "worker-cycle",
                session_id,
                "2026-10-07T20:05:00.000000Z",
                "sha256:" + "b" * 64,
                2,
                400,
                400,
                1,
                1,
                canonical_json(worker_payload),
                canonical_hash(worker_payload),
            ),
        )
        repository.connection.execute(
            """INSERT INTO burn_in_shadow_decision_cycles
               (cycle_id,session_id,run_id,observed_at,config_hash,source_1h_candles,
                derived_candles,processed_candles,emitted_decisions,directional_decisions,
                staged_shadow_intents,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "decision-cycle",
                session_id,
                "decision-run",
                "2026-10-07T20:05:00.000000Z",
                "sha256:" + "c" * 64,
                400,
                100,
                500,
                500,
                0,
                0,
                canonical_json(decision_payload),
                canonical_hash(decision_payload),
            ),
        )
        repository.connection.commit()

    first = complete_scheduled_shadow_day(config, project_root=root, as_of=CLOSE)
    second = complete_scheduled_shadow_day(config, project_root=root, as_of=CLOSE)
    assert first["receipt_id"] == second["receipt_id"]
    assert first["network_read_used"] is True
    assert first["broker_write_performed"] is False
    assert first["regime_annotation_recorded"] is False


def test_schedule_rejects_authority_widening_and_late_start(tmp_path: Path) -> None:
    root = _project(tmp_path)
    path = root / "config/burn-in.phase12c.schedule.v1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveShadowScheduleConfigError, match="invalid or unsafe"):
        load_prospective_shadow_schedule(path)

    config = load_prospective_shadow_schedule(
        ROOT / "config/burn-in.phase12c.schedule.v1.json"
    )
    late = START.replace(minute=46)
    target = inspect_scheduled_shadow_target(config, as_of=late, action="START")
    assert target["eligible"] is False
    assert target["reason"] == "OUTSIDE_ACTION_WINDOW"
