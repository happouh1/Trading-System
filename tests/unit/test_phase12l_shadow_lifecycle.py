from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from trading_system.paper.prospective_shadow_audit import (
    audit_late_scheduled_shadow_day,
    load_prospective_shadow_audit_config,
    shadow_audit_status,
)
from trading_system.paper.prospective_shadow_lifecycle import (
    load_shadow_lifecycle_config,
    record_shadow_operation_event,
)
from trading_system.paper.prospective_shadow_orchestrator import (
    load_prospective_shadow_schedule,
    start_scheduled_shadow_day,
)
from trading_system.paper.prospective_shadow_watchdog import (
    inspect_prospective_shadow_watchdog,
    load_prospective_shadow_watchdog_config,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12h.schedule.v1.json",
        "config/burn-in.phase12h.audit.v1.json",
        "config/burn-in.phase12l.lifecycle.v1.json",
        "config/burn-in.phase12l.watchdog.v1.json",
        "config/burn-in.phase12h.plan.v1.json",
        "config/burn-in.phase12h.launch.v1.json",
        "config/desktop.phase12h.runtime-lock.v1.json",
        "config/webull.sandbox.v1.yaml",
        "config/webull.phase12h.readonly.v1.json",
        "config/webull.phase12h.decisions.v1.json",
        "config/thresholds.phase1e.v1.yaml",
        "config/paper.phase3b.v1.yaml",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def _post_close(root: Path, session_id: str, plan_id: str, config_hash: str) -> None:
    payload = {
        "receipt_id": "late-post-close",
        "session_id": session_id,
        "plan_id": plan_id,
        "broker_write_performed": False,
    }
    with SQLiteRepository(root / "webull-sandbox.sqlite") as repository:
        repository.migrate()
        repository.connection.execute(
            """INSERT INTO paper_shadow_orchestration_receipts
               (receipt_id,session_id,plan_id,market_day,action,scheduled_at,observed_at,
                status,config_hash,network_read_used,broker_write_performed,payload_json,
                payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "late-post-close",
                session_id,
                plan_id,
                "2026-10-19",
                "POST_CLOSE",
                "2026-10-19T20:05:00.000000Z",
                "2026-10-19T20:30:00.000000Z",
                "POST_CLOSE_CYCLES_COMPLETED",
                config_hash,
                1,
                0,
                canonical_json(payload),
                canonical_hash(payload),
            ),
        )
        repository.connection.commit()


def test_late_audit_preserves_lateness_and_closes_missing_status(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule = load_prospective_shadow_schedule(
        root / "config/burn-in.phase12h.schedule.v1.json"
    )
    audit = load_prospective_shadow_audit_config(
        root / "config/burn-in.phase12h.audit.v1.json"
    )
    session_id = "burn-in-shadow-20261019-01"
    start_scheduled_shadow_day(
        schedule,
        schedule_path="config/burn-in.phase12h.schedule.v1.json",
        project_root=root,
        as_of=datetime(2026, 10, 19, 13, 30, tzinfo=UTC),
    )
    _post_close(root, session_id, schedule.plan_id, schedule.config_hash)
    result = audit_late_scheduled_shadow_day(
        schedule,
        audit,
        project_root=root,
        session_id=session_id,
        as_of=datetime(2026, 10, 23, 11, 0, tzinfo=UTC),
    )
    assert result["status"] == "COMPLETE_LATE_AUDIT"
    assert result["late_audit"] is True
    assert result["qualifies_zero_incident_cohort"] is False
    assert result["backfill_performed"] is False
    status = shadow_audit_status(
        schedule,
        audit,
        project_root=root,
        as_of=datetime(2026, 10, 23, 11, 1, tzinfo=UTC),
    )
    assert status["counts"]["COMPLETE_LATE_AUDIT"] == 1  # type: ignore[index]


def test_watchdog_accepts_active_phase12l_collection(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule = load_prospective_shadow_schedule(
        root / "config/burn-in.phase12h.schedule.v1.json"
    )
    session_id = "burn-in-shadow-20261019-01"
    start_scheduled_shadow_day(
        schedule,
        schedule_path="config/burn-in.phase12h.schedule.v1.json",
        project_root=root,
        as_of=datetime(2026, 10, 19, 13, 30, tzinfo=UTC),
    )
    lifecycle = load_shadow_lifecycle_config(
        root / "config/burn-in.phase12l.lifecycle.v1.json"
    )
    record_shadow_operation_event(
        lifecycle,
        project_root=root,
        session_id=session_id,
        operation="POST_CLOSE",
        state="STARTED",
        stage="COLLECTION",
        observed_at=datetime(2026, 10, 19, 20, 6, tzinfo=UTC),
    )
    watchdog = load_prospective_shadow_watchdog_config(
        root / "config/burn-in.phase12l.watchdog.v1.json"
    )
    result = inspect_prospective_shadow_watchdog(
        watchdog,
        project_root=root,
        as_of=datetime(2026, 10, 19, 20, 20, tzinfo=UTC),
    )
    assert result["status"] == "HEALTHY_POST_CLOSE_RUNNING"
    assert result["alert_required"] is False
    assert result["post_close_lifecycle_state"] == "STARTED"


def test_phase12l_scripts_keep_broker_authority_disabled() -> None:
    close = (ROOT / "scripts/run-phase12l-shadow-close.ps1").read_text(
        encoding="utf-8"
    )
    audit = (ROOT / "scripts/run-phase12l-shadow-audit.ps1").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "scripts/install-phase12l-shadow-tasks.ps1").read_text(
        encoding="utf-8"
    )
    assert "scheduled-shadow-operation-event" in close
    assert "scheduled-shadow-operation-event" in audit
    assert "run-phase12l-shadow-close.ps1" in installer
    assert "run-phase12l-shadow-audit.ps1" in installer
    assert "$LASTEXITCODE" not in installer
    authority = json.loads(
        (ROOT / "config/burn-in.phase12l.lifecycle.v1.json").read_text()
    )["authority"]
    assert authority["broker_writes_enabled"] is False
    assert authority["order_api_enabled"] is False
