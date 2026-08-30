from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5e.v1.yaml"


def _local_config(tmp_path: Path) -> Path:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["storage"]["workspace_root"] = "."
    path = tmp_path / "resilience.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_phase5e_cli_backup_restore_and_retention_flow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    source = tmp_path / "source.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO evidence VALUES (1, 'phase5e')")
    connection.commit()
    connection.close()
    registry = tmp_path / "registry.sqlite"
    config = _local_config(tmp_path)
    backup_input = tmp_path / "backup.json"
    backup_input.write_text(
        json.dumps(
            {
                "source_path": "source.sqlite",
                "known_at": now.isoformat(),
                "source_revision": "sha256:phase5e-cli",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "backup-database",
            "--config",
            str(config),
            "--input",
            str(backup_input),
            "--database",
            str(registry),
        ]
    ) == 0
    backup = json.loads(capsys.readouterr().out)
    assert backup["source_opened_read_only"] is True
    assert backup["network_used"] is False
    assert backup["broker_write_performed"] is False
    backup_id = str(backup["manifest"]["backup_id"])
    verify_input = tmp_path / "verify.json"
    verify_input.write_text(
        json.dumps(
            {
                "backup_id": backup_id,
                "known_at": (now + timedelta(seconds=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "verify-restore",
            "--config",
            str(config),
            "--input",
            str(verify_input),
            "--database",
            str(registry),
        ]
    ) == 0
    verification = json.loads(capsys.readouterr().out)
    assert verification["verification"]["status"] == "VERIFIED"
    assert verification["isolated_restore_only"] is True
    assert verification["promotion_performed"] is False
    assert main(
        [
            "operations",
            "retention-status",
            "--config",
            str(config),
            "--database",
            str(registry),
            "--as-of",
            now.isoformat(),
        ]
    ) == 0
    retention = json.loads(capsys.readouterr().out)
    assert retention["deletion_performed"] is False
    assert retention["report"]["protected_backup_ids"] == [backup_id]


def test_phase5e_migration_copies_and_foreign_keys(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "registry.sqlite") as repository:
        repository.migrate()
        tables = {
            str(row[0])
            for row in repository.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "operations_backup_manifests",
        "operations_restore_verifications",
        "operations_retention_reports",
    }.issubset(tables)
    root_copy = ROOT / "migrations" / "026_phase_5e_resilience.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "026_phase_5e_resilience.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
