from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.desktop import (
    build_local_schema_upgrade_plan,
    load_upgrade_plan_config,
)
from trading_system.desktop.upgrade_plan import UpgradePlanConfigError
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9k.v1.yaml"
REQUIRED_TABLES = (
    "paper_burn_in_assessments",
    "paper_certification_assessments",
    "paper_operator_snapshots",
    "paper_rollout_gate_assessments",
    "paper_sandbox_lease_assessments",
    "paper_stage_authorization_assessments",
)


def _copy_config_chain(root: Path) -> None:
    for source in (
        "config/desktop.phase9g.v1.yaml",
        "config/desktop.phase9h.v1.yaml",
        "config/desktop.phase9i.v1.yaml",
        "config/desktop.phase9j.v1.yaml",
        "config/desktop.phase9k.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/paper.phase3b.v1.yaml",
        "config/webull.sandbox.v1.yaml",
    ):
        target = root / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    python = root / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("fixture", encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_database_is_blocked_without_side_effects(tmp_path: Path) -> None:
    _copy_config_chain(tmp_path)
    config = load_upgrade_plan_config(CONFIG)
    first = build_local_schema_upgrade_plan(config, project_root=tmp_path)
    assert first == build_local_schema_upgrade_plan(config, project_root=tmp_path)
    assert first.database_state == "MISSING"
    assert first.plan_status == "BLOCKED"
    assert first.missing_tables == REQUIRED_TABLES
    assert not first.backup_required
    assert not first.migration_executed
    assert not first.database_write_performed


def test_legacy_database_requires_backup_but_is_not_changed(tmp_path: Path) -> None:
    _copy_config_chain(tmp_path)
    database = tmp_path / "webull-sandbox.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE legacy_evidence (value TEXT)")
    before = _digest(database)
    plan = build_local_schema_upgrade_plan(
        load_upgrade_plan_config(CONFIG), project_root=tmp_path
    )
    assert plan.database_state == "AVAILABLE"
    assert plan.plan_status == "REQUIRED"
    assert plan.quick_check == ("ok",)
    assert plan.missing_tables == REQUIRED_TABLES
    assert plan.backup_required
    assert not plan.backup_created
    assert not plan.migration_executed
    assert _digest(database) == before


def test_current_schema_needs_no_upgrade_and_is_not_changed(tmp_path: Path) -> None:
    _copy_config_chain(tmp_path)
    database = tmp_path / "webull-sandbox.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
    before = _digest(database)
    plan = build_local_schema_upgrade_plan(
        load_upgrade_plan_config(CONFIG), project_root=tmp_path
    )
    assert plan.plan_status == "NOT_REQUIRED"
    assert not plan.missing_tables
    assert not plan.backup_required
    assert plan.source_hash is not None
    assert plan.schema_hash is not None
    assert _digest(database) == before


def test_invalid_database_fails_closed_without_replacement(tmp_path: Path) -> None:
    _copy_config_chain(tmp_path)
    database = tmp_path / "webull-sandbox.sqlite"
    database.write_bytes(b"not a sqlite database")
    before = _digest(database)
    plan = build_local_schema_upgrade_plan(
        load_upgrade_plan_config(CONFIG), project_root=tmp_path
    )
    assert plan.database_state == "INVALID"
    assert plan.plan_status == "BLOCKED"
    assert plan.quick_check == ("database_error",)
    assert not plan.backup_required
    assert _digest(database) == before


def test_config_rejects_schema_changes_and_upgrade_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["required_tables"] = raw["required_tables"][:-1]
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(UpgradePlanConfigError, match="required tables"):
        load_upgrade_plan_config(unsafe)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["migration_execution_enabled"] = True
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(UpgradePlanConfigError, match="authority"):
        load_upgrade_plan_config(unsafe)


def test_desktop_cli_renders_read_only_upgrade_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _copy_config_chain(tmp_path)
    with SQLiteRepository(tmp_path / "webull-sandbox.sqlite") as repository:
        repository.migrate()
    assert main(
        [
            "desktop",
            "render-upgrade-plan",
            "--config",
            str(CONFIG),
            "--project-root",
            str(tmp_path),
        ]
    ) == 0
    artifact = json.loads(capsys.readouterr().out)
    document = Path(artifact["output_path"]).read_text(encoding="utf-8")
    assert "Local database preparation" in document
    assert "Migration execution</span><strong>DISABLED" in document
    assert "This plan does not create a backup or change the database." in document
    assert "WEBULL_APP_SECRET" not in document
    assert "<script" not in document
