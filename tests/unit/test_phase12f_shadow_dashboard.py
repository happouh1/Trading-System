from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.paper.prospective_shadow_dashboard import (
    ProspectiveShadowDashboardConfigError,
    load_prospective_shadow_dashboard_config,
    render_prospective_shadow_dashboard,
)

ROOT = Path(__file__).parents[2]
AS_OF = datetime(2026, 10, 7, 22, tzinfo=UTC)
TASKS = (
    "Trading System - Phase 12E Shadow Preflight",
    "Trading System - Phase 12E Shadow Start",
    "Trading System - Phase 12E Shadow Close",
    "Trading System - Phase 12E Shadow Audit",
)


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12e.audit.v1.json",
        "config/burn-in.phase12e.schedule.v1.json",
        "config/burn-in.phase12f.dashboard.v1.json",
        "config/webull.phase12e.readonly.v1.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    snapshot = tmp_path / ".operator-home/phase12f/task-snapshot.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(
        json.dumps(
            {
                "captured_at": "2026-10-07T22:00:00Z",
                "tasks": [
                    {
                        "name": name,
                        "state": "READY",
                        "next_run_at": "2026-10-08T13:00:00Z",
                        "last_run_at": "2026-10-07T20:10:00Z",
                        "last_result": 0 if index == 0 else 267011,
                    }
                    for index, name in enumerate(TASKS)
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_dashboard_is_static_offline_and_deterministic(tmp_path: Path) -> None:
    root = _project(tmp_path)
    config = load_prospective_shadow_dashboard_config(
        root / "config/burn-in.phase12f.dashboard.v1.json"
    )
    first, first_snapshot = render_prospective_shadow_dashboard(
        config, project_root=root, as_of=AS_OF
    )
    second, second_snapshot = render_prospective_shadow_dashboard(
        config, project_root=root, as_of=AS_OF
    )
    output = Path(first.output_path)
    content = output.read_text(encoding="utf-8")
    assert first == second
    assert first_snapshot == second_snapshot
    assert first.overall_status == "GREEN"
    assert first.scheduled_sessions == 20
    assert first.completed_sessions == 0
    assert "MSFT" in content and "SPY" in content
    assert "<script" not in content.lower()
    assert "http://" not in content and "https://" not in content
    assert "WEBULL_APP_SECRET" not in content
    assert first.network_used is False
    assert first.credentials_loaded is False
    assert first.broker_write_performed is False
    assert first.scheduler_modified is False


def test_dashboard_rejects_widened_authority(tmp_path: Path) -> None:
    root = _project(tmp_path)
    path = root / "config/burn-in.phase12f.dashboard.v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["authority"]["broker_writes_enabled"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProspectiveShadowDashboardConfigError, match="invalid or unsafe"):
        load_prospective_shadow_dashboard_config(path)


def test_order_evidence_for_frozen_session_is_red(tmp_path: Path) -> None:
    root = _project(tmp_path)
    database = root / "webull-sandbox.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE paper_orders (session_id TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO paper_orders (session_id) VALUES (?)",
            ("burn-in-shadow-20261008-01",),
        )
    config = load_prospective_shadow_dashboard_config(
        root / "config/burn-in.phase12f.dashboard.v1.json"
    )
    artifact, snapshot = render_prospective_shadow_dashboard(
        config, project_root=root, as_of=AS_OF
    )
    assert artifact.overall_status == "RED"
    assert snapshot["unsafe_evidence"] is True
    assert artifact.broker_write_performed is False


def test_dashboard_cli_emits_artifact_and_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path)
    assert (
        main(
            [
                "paper",
                "scheduled-shadow-dashboard",
                "--config",
                str(root / "config/burn-in.phase12f.dashboard.v1.json"),
                "--as-of",
                AS_OF.isoformat(),
                "--project-root",
                str(root),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifact"]["overall_status"] == "GREEN"
    assert payload["snapshot"]["scheduled_sessions"] == 20
    assert payload["snapshot"]["release_authorized"] is False
