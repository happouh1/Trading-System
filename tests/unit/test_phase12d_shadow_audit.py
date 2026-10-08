from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.paper.prospective_shadow_audit import (
    ProspectiveShadowAuditConfig,
    ProspectiveShadowAuditConfigError,
    audit_scheduled_shadow_day,
    inspect_shadow_audit_target,
    load_prospective_shadow_audit_config,
    shadow_audit_status,
)
from trading_system.paper.prospective_shadow_orchestrator import (
    ProspectiveShadowScheduleConfig,
    load_prospective_shadow_schedule,
    start_scheduled_shadow_day,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
START = datetime(2026, 10, 7, 13, 30, tzinfo=UTC)
AUDIT = datetime(2026, 10, 7, 23, 10, tzinfo=UTC)


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12c.schedule.v1.json",
        "config/burn-in.phase12c.launch.v1.json",
        "config/burn-in.phase12c.plan.v1.json",
        "config/burn-in.phase12d.audit.v1.json",
        "config/desktop.phase12c.runtime-lock.v1.json",
        "config/paper.phase3b.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/webull.sandbox.v1.yaml",
        "config/webull.phase12c.readonly.v1.json",
        "config/webull.phase12c.decisions.v1.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def _configs(
    root: Path,
) -> tuple[ProspectiveShadowScheduleConfig, ProspectiveShadowAuditConfig]:
    schedule = load_prospective_shadow_schedule(
        root / "config/burn-in.phase12c.schedule.v1.json"
    )
    audit = load_prospective_shadow_audit_config(
        root / "config/burn-in.phase12d.audit.v1.json"
    )
    return schedule, audit


def test_phase12d_config_and_dst_audit_windows_are_exact(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule, audit = _configs(root)
    target = inspect_shadow_audit_target(schedule, audit, as_of=AUDIT)
    assert target["eligible"] is True
    assert target["session_id"] == "burn-in-shadow-20261007-01"
    assert target["audit_at"] == AUDIT
    assert (
        inspect_shadow_audit_target(
            schedule,
            audit,
            as_of=datetime(2026, 11, 4, 0, 10, tzinfo=UTC),
        )["session_id"]
        == "burn-in-shadow-20261103-01"
    )


def test_missing_start_is_recorded_once_without_retry(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule, audit = _configs(root)
    first = audit_scheduled_shadow_day(
        schedule, audit, project_root=root, as_of=AUDIT
    )
    second = audit_scheduled_shadow_day(
        schedule, audit, project_root=root, as_of=AUDIT
    )
    assert first == second
    assert first["status"] == "INCOMPLETE_START"
    assert first["missing_components"] == [
        "START_RECEIPT",
        "POST_CLOSE_RECEIPT",
    ]
    assert first["session_retry_performed"] is False
    assert first["backfill_performed"] is False
    status = shadow_audit_status(schedule, audit, project_root=root, as_of=AUDIT)
    counts = status["counts"]
    assert isinstance(counts, Mapping)
    assert counts["INCOMPLETE_START"] == 1
    assert status["release_authorized"] is False


def test_complete_receipts_produce_complete_daily_audit(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule, audit = _configs(root)
    start = start_scheduled_shadow_day(
        schedule,
        schedule_path="config/burn-in.phase12c.schedule.v1.json",
        project_root=root,
        as_of=START,
    )
    payload = {
        "receipt_id": "post-close-receipt",
        "action": "POST_CLOSE",
        "status": "POST_CLOSE_CYCLES_COMPLETED",
        "session_id": "burn-in-shadow-20261007-01",
        "plan_id": schedule.plan_id,
        "market_day": "2026-10-07",
        "scheduled_at": {"__datetime__": "2026-10-07T20:05:00.000000Z"},
        "observed_at": {"__datetime__": "2026-10-07T20:05:00.000000Z"},
        "schedule_config_hash": schedule.config_hash,
        "network_read_used": True,
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
                "post-close-receipt",
                "burn-in-shadow-20261007-01",
                schedule.plan_id,
                "2026-10-07",
                "POST_CLOSE",
                "2026-10-07T20:05:00.000000Z",
                "2026-10-07T20:05:00.000000Z",
                "POST_CLOSE_CYCLES_COMPLETED",
                schedule.config_hash,
                1,
                0,
                canonical_json(payload),
                canonical_hash(payload),
            ),
        )
        repository.connection.commit()
    result = audit_scheduled_shadow_day(
        schedule, audit, project_root=root, as_of=AUDIT
    )
    assert result["status"] == "COMPLETE"
    assert result["start_receipt_id"] == start["receipt_id"]
    assert result["post_close_receipt_id"] == "post-close-receipt"
    assert result["broker_write_detected"] is False


def test_authority_widening_and_early_audit_fail_closed(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule, audit = _configs(root)
    raw = json.loads(
        (root / "config/burn-in.phase12d.audit.v1.json").read_text(encoding="utf-8")
    )
    raw["authority"]["network_enabled"] = True
    unsafe = root / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveShadowAuditConfigError, match="invalid or unsafe"):
        load_prospective_shadow_audit_config(unsafe)
    with pytest.raises(ValueError, match="not eligible"):
        audit_scheduled_shadow_day(
            schedule,
            audit,
            project_root=root,
            as_of=datetime(2026, 10, 7, 23, 9, tzinfo=UTC),
        )
