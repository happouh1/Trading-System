from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.paper.prospective_shadow_audit import (
    load_prospective_shadow_audit_config,
)
from trading_system.paper.prospective_shadow_orchestrator import (
    inspect_scheduled_shadow_preflight,
    load_prospective_shadow_schedule,
)

ROOT = Path(__file__).parents[2]


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12e.schedule.v1.json",
        "config/burn-in.phase12e.launch.v1.json",
        "config/burn-in.phase12e.plan.v1.json",
        "config/burn-in.phase12e.audit.v1.json",
        "config/desktop.phase12e.runtime-lock.v1.json",
        "config/paper.phase3b.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/webull.phase12e.readonly.v1.json",
        "config/webull.phase12e.decisions.v1.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def test_replacement_cohort_is_exact_and_preflight_is_read_only() -> None:
    schedule_path = ROOT / "config/burn-in.phase12e.schedule.v1.json"
    schedule = load_prospective_shadow_schedule(schedule_path)
    assert schedule.plan_id == "prospective_burn_in_plan_04652270247827fa2077543c1a61edfd"
    assert len(schedule.sessions) == 20
    assert schedule.sessions[0].market_day.isoformat() == "2026-10-08"
    assert schedule.sessions[-1].market_day.isoformat() == "2026-11-04"
    assert schedule.sessions[-1].open_at.hour == 14
    result = inspect_scheduled_shadow_preflight(
        schedule,
        schedule_path=schedule_path,
        project_root=ROOT,
        as_of=datetime(2026, 10, 8, 13, 25, tzinfo=UTC),
    )
    assert result["eligible"] is True
    assert result["reason"] == "PREFLIGHT_READY"
    assert result["session_started"] is False
    assert result["network_used"] is False
    assert result["broker_write_performed"] is False


def test_replacement_does_not_mutate_failed_cohort() -> None:
    old = json.loads(
        (ROOT / "config/burn-in.phase12c.plan.v1.json").read_text(encoding="utf-8")
    )
    new = json.loads(
        (ROOT / "config/burn-in.phase12e.plan.v1.json").read_text(encoding="utf-8")
    )
    assert old["plan_id"] == "prospective_burn_in_plan_d06259bcd015c6bc17d4bc73477060d0"
    assert new["plan_id"] != old["plan_id"]
    assert old["window_start"]["__datetime__"] == "2026-10-07T13:30:00.000000Z"
    assert new["window_start"]["__datetime__"] == "2026-10-08T13:30:00.000000Z"


def test_audit_is_bound_to_replacement_schedule() -> None:
    audit = load_prospective_shadow_audit_config(
        ROOT / "config/burn-in.phase12e.audit.v1.json"
    )
    assert audit.schedule == "config/burn-in.phase12e.schedule.v1.json"
    assert audit.schedule_file_sha256 == (
        "sha256:ee95527849bdaabe267191ac9456419065b2df30eb8e847d580ade80e6f94974"
    )


def test_preflight_rejects_frozen_identity_drift(tmp_path: Path) -> None:
    root = _project(tmp_path)
    schedule_path = root / "config/burn-in.phase12e.schedule.v1.json"
    schedule = load_prospective_shadow_schedule(schedule_path)
    plan_path = root / "config/burn-in.phase12e.plan.v1.json"
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen plan and runtime identities"):
        inspect_scheduled_shadow_preflight(
            schedule,
            schedule_path=schedule_path,
            project_root=root,
            as_of=datetime(2026, 10, 8, 13, 25, tzinfo=UTC),
        )


def test_installer_hardens_wake_and_disables_superseded_tasks() -> None:
    installer = (ROOT / "scripts/install-phase12e-shadow-tasks.ps1").read_text(
        encoding="utf-8"
    )
    assert "-WakeToRun" in installer
    assert "-AllowStartIfOnBatteries" in installer
    assert "-DontStopIfGoingOnBatteries" in installer
    assert 'Disable-ScheduledTask -TaskName $superseded' in installer
    assert "09:25" in installer
    assert "09:30" in installer
    assert "16:05" in installer
    assert "19:10" in installer
