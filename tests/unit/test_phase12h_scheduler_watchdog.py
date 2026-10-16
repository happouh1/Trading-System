from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from trading_system.paper.prospective_shadow_orchestrator import (
    load_prospective_shadow_schedule,
)
from trading_system.paper.prospective_shadow_watchdog import (
    inspect_prospective_shadow_watchdog,
    load_prospective_shadow_watchdog_config,
)

ROOT = Path(__file__).parents[2]


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12h.watchdog.v1.json",
        "config/burn-in.phase12h.audit.v1.json",
        "config/burn-in.phase12h.schedule.v1.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def test_phase12h_cohort_is_fresh_exact_and_hash_bound() -> None:
    schedule_path = ROOT / "config/burn-in.phase12h.schedule.v1.json"
    schedule = load_prospective_shadow_schedule(schedule_path)
    plan = json.loads(
        (ROOT / "config/burn-in.phase12h.plan.v1.json").read_text(encoding="utf-8")
    )
    assert schedule.plan_id == plan["plan_id"]
    assert len(schedule.sessions) == 20
    assert schedule.sessions[0].market_day.isoformat() == "2026-10-16"
    assert schedule.sessions[-1].market_day.isoformat() == "2026-11-12"
    assert schedule.sessions[-1].open_at.hour == 14
    expected_hash = "sha256:" + hashlib.sha256(
        (ROOT / schedule.plan_path).read_bytes()
    ).hexdigest()
    assert schedule.plan_file_sha256 == expected_hash


def test_watchdog_fails_closed_when_start_receipt_is_missing(tmp_path: Path) -> None:
    root = _project(tmp_path)
    config = load_prospective_shadow_watchdog_config(
        root / "config/burn-in.phase12h.watchdog.v1.json"
    )
    result = inspect_prospective_shadow_watchdog(
        config,
        project_root=root,
        as_of=datetime(2026, 10, 16, 13, 50, tzinfo=UTC),
    )
    assert result["status"] == "ALERT_MISSING_START"
    assert result["alert_required"] is True
    assert result["network_used"] is False
    assert result["database_write_performed"] is False
    assert result["broker_write_performed"] is False


def test_watchdog_accepts_complete_immutable_evidence(tmp_path: Path) -> None:
    root = _project(tmp_path)
    database = root / "webull-sandbox.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE paper_shadow_orchestration_receipts "
            "(session_id TEXT NOT NULL, action TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE paper_shadow_daily_audits "
            "(session_id TEXT NOT NULL, status TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO paper_shadow_orchestration_receipts VALUES (?, ?)",
            (
                ("burn-in-shadow-20261016-01", "START"),
                ("burn-in-shadow-20261016-01", "POST_CLOSE"),
            ),
        )
        connection.execute(
            "INSERT INTO paper_shadow_daily_audits VALUES (?, ?)",
            ("burn-in-shadow-20261016-01", "COMPLETE"),
        )
    config = load_prospective_shadow_watchdog_config(
        root / "config/burn-in.phase12h.watchdog.v1.json"
    )
    result = inspect_prospective_shadow_watchdog(
        config,
        project_root=root,
        as_of=datetime(2026, 10, 16, 23, 25, tzinfo=UTC),
    )
    assert result["status"] == "HEALTHY_COMPLETE"
    assert result["alert_required"] is False
    assert result["start_receipt_present"] is True
    assert result["post_close_receipt_present"] is True
    assert result["audit_status"] == "COMPLETE"


def test_installer_uses_s4u_wake_and_three_watchdog_checks() -> None:
    installer = (ROOT / "scripts/install-phase12h-shadow-tasks.ps1").read_text(
        encoding="utf-8"
    )
    assert "-LogonType S4U" in installer
    assert "-WakeToRun" in installer
    assert "RTCWAKE 1" in installer
    assert '"09:50", "16:20", "19:25"' in installer
    assert 'Disable-ScheduledTask -TaskName $superseded' in installer
    assert "Phase 12E Shadow Start" in installer
    assert "WindowsBuiltInRole]::Administrator" in installer
    assert "-Verb RunAs" in installer
    assert "Administrator approval is required" in installer
    assert "write-phase12h-task-snapshot.ps1" in installer


def test_dashboard_preserves_elevated_task_snapshot_when_scheduler_is_protected() -> None:
    renderer = (ROOT / "scripts/render-phase12h-dashboard.ps1").read_text(
        encoding="utf-8"
    )
    watchdog = (ROOT / "scripts/run-phase12h-shadow-watchdog.ps1").read_text(
        encoding="utf-8"
    )
    snapshot = (ROOT / "scripts/write-phase12h-task-snapshot.ps1").read_text(
        encoding="utf-8"
    )
    assert "write-phase12h-task-snapshot.ps1" in renderer
    assert "if (-not (Test-Path -LiteralPath $SnapshotPath -PathType Leaf))" in renderer
    assert "write-phase12h-task-snapshot.ps1" in watchdog
    assert '"Trading System - Phase 12H Shadow Audit"' in snapshot
    assert '"Trading System - Phase 12H Shadow Watchdog"' not in snapshot
    assert "last_result" in snapshot
