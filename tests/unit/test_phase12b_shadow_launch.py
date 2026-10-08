from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.desktop.burn_in_runtime_lock import load_burn_in_runtime_lock
from trading_system.paper import RuntimeState
from trading_system.paper.prospective_shadow_launch import (
    ProspectiveShadowLaunchConfigError,
    load_prospective_shadow_launch_config,
    start_prospective_shadow_session,
)
from trading_system.persistence import SQLiteRepository
from trading_system.webull.burn_in_decision_worker import (
    load_burn_in_decision_worker_config,
)
from trading_system.webull.burn_in_worker import load_burn_in_worker_config

ROOT = Path(__file__).parents[2]
START = datetime(2026, 9, 28, 13, 30, tzinfo=UTC)


def _project(tmp_path: Path) -> Path:
    for relative in (
        "config/burn-in.phase12b.launch.v1.json",
        "config/desktop.phase12b.runtime-lock.v1.json",
        "config/paper.phase3b.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/webull.phase12b.readonly.v1.json",
        "config/webull.phase12b.decisions.v1.json",
        ".operator-home/phase12a/burn-in-plan-20260928.json",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def test_phase12b_checked_in_identities_are_exact_and_non_executable() -> None:
    launch = load_prospective_shadow_launch_config(
        ROOT / "config/burn-in.phase12b.launch.v1.json"
    )
    lock = load_burn_in_runtime_lock(
        ROOT / "config/desktop.phase12b.runtime-lock.v1.json"
    )
    worker = load_burn_in_worker_config(
        ROOT / "config/webull.phase12b.readonly.v1.json"
    )
    decisions = load_burn_in_decision_worker_config(
        ROOT / "config/webull.phase12b.decisions.v1.json"
    )
    assert launch.symbols == ("MSFT", "SPY")
    assert worker.symbols == launch.symbols
    assert worker.plan_id == decisions.plan_id == launch.plan_id == lock.plan_id
    assert worker.network_read_enabled
    assert not lock.retrospective_baseline_disclosed


def test_phase12b_launch_is_idempotent_and_shadow_only(tmp_path: Path) -> None:
    root = _project(tmp_path)
    first = start_prospective_shadow_session(
        database="phase12b.sqlite",
        config_path="config/burn-in.phase12b.launch.v1.json",
        runtime_lock_path="config/desktop.phase12b.runtime-lock.v1.json",
        project_root=root,
        session_id="burn-in-shadow-20260928-01",
        started_at=START,
    )
    second = start_prospective_shadow_session(
        database="phase12b.sqlite",
        config_path="config/burn-in.phase12b.launch.v1.json",
        runtime_lock_path="config/desktop.phase12b.runtime-lock.v1.json",
        project_root=root,
        session_id="burn-in-shadow-20260928-01",
        started_at=START,
    )
    assert first["state"] is RuntimeState.SHADOW
    assert first["session_inserted"] is True
    assert first["binding_inserted"] is True
    assert second["session_inserted"] is False
    assert second["binding_inserted"] is False
    assert not first["network_used"]
    assert not first["broker_write_performed"]
    with SQLiteRepository(root / "phase12b.sqlite") as repository:
        assert repository.connection.execute(
            "SELECT plan_id FROM paper_burn_in_session_bindings WHERE session_id=?",
            ("burn-in-shadow-20260928-01",),
        ).fetchone() == (first["plan_id"],)


def test_phase12b_rejects_plan_tampering_before_database_write(tmp_path: Path) -> None:
    root = _project(tmp_path)
    plan = root / ".operator-home/phase12a/burn-in-plan-20260928.json"
    plan.write_text(plan.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="plan bytes"):
        start_prospective_shadow_session(
            database="phase12b.sqlite",
            config_path="config/burn-in.phase12b.launch.v1.json",
            runtime_lock_path="config/desktop.phase12b.runtime-lock.v1.json",
            project_root=root,
            session_id="burn-in-shadow-20260928-01",
            started_at=START,
        )
    assert not (root / "phase12b.sqlite").exists()


def test_phase12b_rejects_authority_widening(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.json"
    raw = json.loads(
        (ROOT / "config/burn-in.phase12b.launch.v1.json").read_text(encoding="utf-8")
    )
    raw["authority"]["broker_writes_enabled"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveShadowLaunchConfigError, match="invalid or unsafe"):
        load_prospective_shadow_launch_config(path)
