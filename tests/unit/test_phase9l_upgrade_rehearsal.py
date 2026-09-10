from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.desktop import (
    load_upgrade_rehearsal_config,
    rehearse_schema_upgrade,
)
from trading_system.desktop.upgrade_rehearsal import UpgradeRehearsalConfigError

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9l.v1.yaml"


def _root(tmp_path: Path) -> Path:
    for source in ("config/desktop.phase9k.v1.yaml", "config/desktop.phase9l.v1.yaml"):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    fixture = tmp_path / "fixtures/upgrade-rehearsal/legacy.sqlite"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(fixture) as connection:
        connection.executescript(
            """
            CREATE TABLE legacy_fixture (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO legacy_fixture VALUES (1, 'preserve-me');
            """
        )
    return fixture


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_copy_rehearsal_migrates_and_restores_without_changing_source(tmp_path: Path) -> None:
    source = _root(tmp_path)
    before = _digest(source)
    result = rehearse_schema_upgrade(
        load_upgrade_rehearsal_config(CONFIG),
        project_root=tmp_path,
        source_path="fixtures/upgrade-rehearsal/legacy.sqlite",
        source_revision="TEST_ONLY_LEGACY_V1",
    )
    assert result.status == "VERIFIED"
    assert result.source_hash_before == result.source_hash_after
    assert result.backup_hash == result.restored_hash
    assert result.preserved_row_counts == (("legacy_fixture", 1),)
    assert not result.missing_required_tables
    assert not result.source_database_write_performed
    assert not result.restore_promoted
    assert not result.production_migration_executed
    assert _digest(source) == before
    with sqlite3.connect(tmp_path / result.upgraded_path) as connection:
        value = connection.execute("SELECT value FROM legacy_fixture").fetchone()
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert value == ("preserve-me",)
    assert set(result.required_tables) <= tables


def test_rehearsal_restart_is_deterministic_and_does_not_overwrite(tmp_path: Path) -> None:
    _root(tmp_path)
    config = load_upgrade_rehearsal_config(CONFIG)
    first = rehearse_schema_upgrade(
        config,
        project_root=tmp_path,
        source_path="fixtures/upgrade-rehearsal/legacy.sqlite",
        source_revision="TEST_ONLY_RESTART_V1",
    )
    artifact = tmp_path / first.upgraded_path
    modified = artifact.stat().st_mtime_ns
    second = rehearse_schema_upgrade(
        config,
        project_root=tmp_path,
        source_path="fixtures/upgrade-rehearsal/legacy.sqlite",
        source_revision="TEST_ONLY_RESTART_V1",
    )
    assert first == second
    assert artifact.stat().st_mtime_ns == modified


def test_existing_artifact_tampering_fails_closed(tmp_path: Path) -> None:
    _root(tmp_path)
    config = load_upgrade_rehearsal_config(CONFIG)
    result = rehearse_schema_upgrade(
        config,
        project_root=tmp_path,
        source_path="fixtures/upgrade-rehearsal/legacy.sqlite",
        source_revision="TEST_ONLY_TAMPER_V1",
    )
    (tmp_path / result.upgraded_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact conflicts"):
        rehearse_schema_upgrade(
            config,
            project_root=tmp_path,
            source_path="fixtures/upgrade-rehearsal/legacy.sqlite",
            source_revision="TEST_ONLY_TAMPER_V1",
        )


def test_real_database_paths_and_revisions_are_rejected(tmp_path: Path) -> None:
    source = _root(tmp_path)
    outside = tmp_path / "webull-sandbox.sqlite"
    outside.write_bytes(source.read_bytes())
    config = load_upgrade_rehearsal_config(CONFIG)
    with pytest.raises(ValueError, match="TEST_ONLY"):
        rehearse_schema_upgrade(
            config,
            project_root=tmp_path,
            source_path="fixtures/upgrade-rehearsal/legacy.sqlite",
            source_revision="REAL_DATABASE",
        )
    with pytest.raises(ValueError, match="test-only fixture"):
        rehearse_schema_upgrade(
            config,
            project_root=tmp_path,
            source_path="webull-sandbox.sqlite",
            source_revision="TEST_ONLY_INVALID_LOCATION",
        )


def test_config_rejects_weakened_verification_and_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["verification"]["verify_restore_hash"] = False
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(UpgradeRehearsalConfigError, match="verification"):
        load_upgrade_rehearsal_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["production_migration_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(UpgradeRehearsalConfigError, match="authority"):
        load_upgrade_rehearsal_config(invalid)


def test_rehearsal_cli_returns_machine_readable_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _root(tmp_path)
    assert main(
        [
            "desktop",
            "rehearse-upgrade",
            "--config",
            str(CONFIG),
            "--project-root",
            str(tmp_path),
            "--source",
            "fixtures/upgrade-rehearsal/legacy.sqlite",
            "--source-revision",
            "TEST_ONLY_CLI_V1",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "VERIFIED"
    assert payload["test_only"] is True
    assert payload["source_database_write_performed"] is False
    assert payload["restore_promoted"] is False
