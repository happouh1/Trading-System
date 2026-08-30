from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.operations import (
    IntegrityStatus,
    OperationsResilienceConfigError,
    OperationsResilienceRegistry,
    OperationsResilienceService,
    load_operations_resilience_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5e.v1.yaml"
AS_OF = datetime(2026, 8, 30, 16, tzinfo=UTC)


def _local_config(tmp_path: Path) -> Path:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["storage"]["workspace_root"] = "."
    path = tmp_path / "resilience.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _source(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE parent (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE child (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES parent(id)
            );
            INSERT INTO parent VALUES (1, 'immutable');
            INSERT INTO child VALUES (1, 1);
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_phase5e_config_is_offline_report_only_and_fail_closed(tmp_path: Path) -> None:
    config = load_operations_resilience_config(CONFIG)
    assert config.minimum_retention_days == 30
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["backup_deletion_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsResilienceConfigError, match="offline and inert"):
        load_operations_resilience_config(invalid)


def test_backup_and_isolated_restore_are_content_addressed_and_restart_safe(
    tmp_path: Path,
) -> None:
    config = load_operations_resilience_config(_local_config(tmp_path))
    source = tmp_path / "source.sqlite"
    registry_path = tmp_path / "registry.sqlite"
    _source(source)
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        service = OperationsResilienceService(config, registry)
        first = service.create_backup(
            source_path="source.sqlite",
            known_at=AS_OF,
            source_revision="sha256:source-v1",
        )
        second = service.create_backup(
            source_path="source.sqlite",
            known_at=AS_OF + timedelta(seconds=1),
            source_revision="sha256:source-v1",
        )
        assert first.artifact_hash == second.artifact_hash
        assert first.artifact_path == second.artifact_path
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        verification = OperationsResilienceService(config, registry).verify_restore(
            backup_id=first.backup_id,
            known_at=AS_OF + timedelta(minutes=1),
        )
    assert verification.status is IntegrityStatus.VERIFIED
    assert verification.expected_hash == verification.actual_hash
    assert verification.promoted is False
    assert (tmp_path / verification.restored_path).is_file()


def test_backup_is_snapshot_and_later_source_mutation_does_not_change_it(tmp_path: Path) -> None:
    config = load_operations_resilience_config(_local_config(tmp_path))
    source = tmp_path / "source.sqlite"
    _source(source)
    with SQLiteRepository(tmp_path / "registry.sqlite") as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        service = OperationsResilienceService(config, registry)
        manifest = service.create_backup(
            source_path="source.sqlite",
            known_at=AS_OF,
            source_revision="sha256:before-mutation",
        )
        connection = sqlite3.connect(source)
        connection.execute("INSERT INTO parent VALUES (2, 'later')")
        connection.commit()
        connection.close()
        verification = service.verify_restore(
            backup_id=manifest.backup_id,
            known_at=AS_OF + timedelta(minutes=1),
        )
    restored = sqlite3.connect(tmp_path / verification.restored_path)
    try:
        count = int(restored.execute("SELECT COUNT(*) FROM parent").fetchone()[0])
    finally:
        restored.close()
    assert count == 1


def test_corrupted_artifact_is_rejected_before_restore(tmp_path: Path) -> None:
    config = load_operations_resilience_config(_local_config(tmp_path))
    source = tmp_path / "source.sqlite"
    _source(source)
    with SQLiteRepository(tmp_path / "registry.sqlite") as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        service = OperationsResilienceService(config, registry)
        manifest = service.create_backup(
            source_path="source.sqlite",
            known_at=AS_OF,
            source_revision="sha256:corruption-case",
        )
        artifact = tmp_path / manifest.artifact_path
        artifact.write_bytes(artifact.read_bytes() + b"corrupt")
        with pytest.raises(ValueError, match="hash mismatch"):
            service.verify_restore(
                backup_id=manifest.backup_id,
                known_at=AS_OF + timedelta(minutes=1),
            )


def test_retention_is_partitioned_report_only_and_never_deletes(tmp_path: Path) -> None:
    config = load_operations_resilience_config(_local_config(tmp_path))
    source = tmp_path / "source.sqlite"
    _source(source)
    with SQLiteRepository(tmp_path / "registry.sqlite") as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        service = OperationsResilienceService(config, registry)
        old = service.create_backup(
            source_path="source.sqlite",
            known_at=AS_OF - timedelta(days=31),
            source_revision="sha256:old",
        )
        current = service.create_backup(
            source_path="source.sqlite",
            known_at=AS_OF,
            source_revision="sha256:current",
        )
        report = registry.retention_report(AS_OF)
        registry.insert_retention_report(report)
    assert report.review_eligible_backup_ids == (old.backup_id,)
    assert report.protected_backup_ids == (current.backup_id,)
    assert report.deletion_performed is False
    assert (tmp_path / old.artifact_path).is_file()


def test_backup_rejects_parent_traversal(tmp_path: Path) -> None:
    config = load_operations_resilience_config(_local_config(tmp_path))
    with SQLiteRepository(tmp_path / "registry.sqlite") as repository:
        repository.migrate()
        service = OperationsResilienceService(
            config, OperationsResilienceRegistry(repository, config)
        )
        with pytest.raises(ValueError, match="contained relative"):
            service.create_backup(
                source_path="../outside.sqlite",
                known_at=AS_OF,
                source_revision="sha256:outside",
            )
