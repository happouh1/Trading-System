from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.operations import (
    OperationsConfigError,
    OperationsManifest,
    ReadinessStatus,
    inspect_component,
    load_operations_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5a.v1.yaml"
KNOWN_AT = datetime(2026, 8, 30, 15, tzinfo=UTC)


def _ready_database(path: Path) -> None:
    config = load_operations_config(CONFIG)
    tables = sorted({table for values in config.components.values() for table in values})
    with sqlite3.connect(path) as connection:
        for table in tables:
            if table in {"paper_reconciliations", "webull_reconciliations"}:
                connection.execute(f'CREATE TABLE "{table}" (matched INTEGER NOT NULL)')
                connection.execute(f'INSERT INTO "{table}" VALUES (1)')
            else:
                connection.execute(f'CREATE TABLE "{table}" (value TEXT NOT NULL)')
                connection.execute(f'INSERT INTO "{table}" VALUES (?)', (f"evidence:{table}",))


def test_phase5a_config_is_strict_and_inspection_only(tmp_path: Path) -> None:
    config = load_operations_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["workflow_execution_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsConfigError, match="inspection-only"):
        load_operations_config(path)


def test_missing_database_fails_closed_and_is_deterministic(tmp_path: Path) -> None:
    config = load_operations_config(CONFIG)
    missing = tmp_path / "missing.sqlite"
    first = inspect_component(
        config,
        component="CORE_RESEARCH",
        database_label="research",
        database_path=missing,
        known_at=KNOWN_AT,
    )
    second = inspect_component(
        config,
        component="CORE_RESEARCH",
        database_label="research",
        database_path=missing,
        known_at=KNOWN_AT,
    )
    assert first == second
    assert first.status is ReadinessStatus.NOT_READY
    assert first.reasons == ("DATABASE_NOT_FOUND",)


def test_ready_component_requires_every_table_to_contain_evidence(tmp_path: Path) -> None:
    config = load_operations_config(CONFIG)
    database = tmp_path / "ready.sqlite"
    _ready_database(database)
    result = inspect_component(
        config,
        component="OPTIONS",
        database_label="research",
        database_path=database,
        known_at=KNOWN_AT,
    )
    assert result.status is ReadinessStatus.READY
    assert result.reasons == ()
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM option_capital_reports")
    result = inspect_component(
        config,
        component="OPTIONS",
        database_label="research",
        database_path=database,
        known_at=KNOWN_AT,
    )
    assert result.status is ReadinessStatus.NOT_READY
    assert result.reasons == ("NO_EVIDENCE:option_capital_reports",)


def test_latest_unmatched_reconciliation_fails_closed(tmp_path: Path) -> None:
    config = load_operations_config(CONFIG)
    database = tmp_path / "unmatched.sqlite"
    _ready_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO webull_reconciliations VALUES (0)")
    result = inspect_component(
        config,
        component="WEBULL_SANDBOX",
        database_label="sandbox",
        database_path=database,
        known_at=KNOWN_AT,
    )
    assert result.status is ReadinessStatus.NOT_READY
    assert result.reasons == ("LATEST_RECONCILIATION_UNMATCHED",)


def test_manifest_is_order_independent_and_fail_closed(tmp_path: Path) -> None:
    config = load_operations_config(CONFIG)
    database = tmp_path / "ready.sqlite"
    _ready_database(database)
    evidence = tuple(
        inspect_component(
            config,
            component=component,
            database_label="unified",
            database_path=database,
            known_at=KNOWN_AT,
        )
        for component in config.components
    )
    first = OperationsManifest.create(
        known_at=KNOWN_AT,
        evidence=evidence,
        config_hash=config.config_hash,
        code_version="test",
        source_revision="sha256:fixture",
    )
    second = OperationsManifest.create(
        known_at=KNOWN_AT,
        evidence=tuple(reversed(evidence)),
        config_hash=config.config_hash,
        code_version="test",
        source_revision="sha256:fixture",
    )
    assert first == second
    assert first.status is ReadinessStatus.READY


def test_operations_cli_persists_offline_readiness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_database = tmp_path / "source.sqlite"
    registry_database = tmp_path / "registry.sqlite"
    _ready_database(source_database)
    config = load_operations_config(CONFIG)
    source = tmp_path / "operations.json"
    source.write_text(
        json.dumps(
            {
                "known_at": KNOWN_AT.isoformat(),
                "source_revision": "sha256:operations-cli",
                "databases": {
                    component: {"label": "fixture", "path": source_database.name}
                    for component in config.components
                },
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "inspect",
                "--config",
                str(CONFIG),
                "--input",
                str(source),
                "--registry-database",
                str(registry_database),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["manifest"]["status"] == "READY"
    manifest_id = output["manifest"]["manifest_id"]
    assert (
        main(
            [
                "operations",
                "status",
                "--registry-database",
                str(registry_database),
                "--manifest-id",
                manifest_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "READY"
    assert status["component_count"] == 7


def test_operations_cli_refuses_to_write_into_source_database(tmp_path: Path) -> None:
    source_database = tmp_path / "source.sqlite"
    _ready_database(source_database)
    config = load_operations_config(CONFIG)
    source = tmp_path / "operations.json"
    source.write_text(
        json.dumps(
            {
                "known_at": KNOWN_AT.isoformat(),
                "source_revision": "sha256:separation",
                "databases": {
                    component: {"label": "fixture", "path": source_database.name}
                    for component in config.components
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="separate"):
        main(
            [
                "operations",
                "inspect",
                "--config",
                str(CONFIG),
                "--input",
                str(source),
                "--registry-database",
                str(source_database),
            ]
        )
