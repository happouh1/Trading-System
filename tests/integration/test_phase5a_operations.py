from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.operations import (
    OperationsManifest,
    OperationsRegistry,
    inspect_component,
    load_operations_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5a.v1.yaml"


def test_phase5a_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    registry_path = tmp_path / "registry.sqlite"
    config = load_operations_config(CONFIG)
    with sqlite3.connect(source) as connection:
        for table in sorted({item for values in config.components.values() for item in values}):
            if table in {"paper_reconciliations", "webull_reconciliations"}:
                connection.execute(f'CREATE TABLE "{table}" (matched INTEGER NOT NULL)')
                connection.execute(f'INSERT INTO "{table}" VALUES (1)')
            else:
                connection.execute(f'CREATE TABLE "{table}" (value TEXT NOT NULL)')
                connection.execute(f'INSERT INTO "{table}" VALUES (?)', (table,))
    known_at = datetime(2026, 8, 30, 16, tzinfo=UTC)
    evidence = tuple(
        inspect_component(
            config,
            component=component,
            database_label="fixture",
            database_path=source,
            known_at=known_at,
        )
        for component in config.components
    )
    manifest = OperationsManifest.create(
        known_at=known_at,
        evidence=evidence,
        config_hash=config.config_hash,
        code_version="test",
        source_revision="sha256:restart",
    )
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        assert registry.insert_manifest(manifest)
        assert not registry.insert_manifest(manifest)
        for item in evidence:
            assert registry.insert_evidence(manifest.manifest_id, item)
            assert not registry.insert_evidence(manifest.manifest_id, item)
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        _, status, count = registry.status(manifest.manifest_id)
        assert status == "READY"
        assert count == 7
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_manifest(replace(manifest, source_revision="sha256:changed"))


def test_phase5a_migration_copies_are_identical() -> None:
    root_copy = ROOT / "migrations" / "022_phase_5a_operations.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "022_phase_5a_operations.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
