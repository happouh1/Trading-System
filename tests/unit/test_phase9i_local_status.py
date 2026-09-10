from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.desktop import inspect_local_operations, load_local_status_config
from trading_system.desktop.local_status import LocalStatusConfigError
from trading_system.paper import (
    PaperMode,
    PaperOperatorRegistry,
    PaperRegistry,
    PaperSession,
    ReconciliationResult,
    RuntimeState,
    load_paper_operator_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9i.v1.yaml"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paper_database(path: Path) -> None:
    created = datetime(2026, 9, 10, 14, 0, tzinfo=UTC)
    with SQLiteRepository(path) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(PaperSession(
            "paper-local-001",
            created,
            PaperMode.SHADOW,
            "test-code",
            "sha256:test-config",
            "fixture-data",
            "XNYS-test",
        ))
        paper.transition("paper-local-001", RuntimeState.STARTING, created, "TEST_START")
        paper.transition(
            "paper-local-001", RuntimeState.SHADOW, created + timedelta(seconds=1), "TEST_READY"
        )
        paper.insert_heartbeat("paper-local-001", created + timedelta(seconds=2))
        paper.insert_checkpoint(
            "paper-local-001",
            "candle-001",
            "1h",
            created + timedelta(seconds=2),
            "sha256:test-state",
            {"fixture": True},
        )
        paper.insert_incident(
            "paper-local-001", created + timedelta(seconds=2), "TEST_INCIDENT"
        )
        paper.insert_reconciliation(ReconciliationResult(
            "reconciliation-001",
            "paper-local-001",
            created + timedelta(seconds=2),
            False,
            ("FIXTURE_DIFFERENCE",),
        ))
        operator = PaperOperatorRegistry(repository)
        snapshot = operator.observe(
            load_paper_operator_config(ROOT / "config/paper.phase9a.v1.yaml"),
            session_id="paper-local-001",
            observed_at=created + timedelta(seconds=3),
            replication_status_hash="sha256:test-replication",
        )
        operator.record_snapshot(snapshot)


def _dashboard_root(root: Path) -> None:
    for source in (
        "config/desktop.phase9g.v1.yaml",
        "config/desktop.phase9h.v1.yaml",
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


def test_missing_database_is_deterministic_and_fail_closed(tmp_path: Path) -> None:
    config = load_local_status_config(CONFIG)
    first = inspect_local_operations(config, project_root=tmp_path)
    assert first == inspect_local_operations(config, project_root=tmp_path)
    assert first.database_state == "MISSING"
    assert first.reason_codes == ("DATABASE_MISSING",)
    assert first.session_id is None
    assert not first.database_write_performed
    assert not first.network_used
    assert not first.credentials_loaded
    assert not first.broker_write_performed


def test_incomplete_database_schema_is_reported_without_migration(tmp_path: Path) -> None:
    database = tmp_path / "webull-sandbox.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    before = _digest(database)
    status = inspect_local_operations(load_local_status_config(CONFIG), project_root=tmp_path)
    assert status.database_state == "SCHEMA_MISSING"
    assert status.reason_codes == ("DATABASE_SCHEMA_MISSING",)
    assert _digest(database) == before


def test_latest_session_status_is_read_without_modifying_database(tmp_path: Path) -> None:
    database = tmp_path / "webull-sandbox.sqlite"
    _paper_database(database)
    before = _digest(database)
    config = load_local_status_config(CONFIG)
    status = inspect_local_operations(config, project_root=tmp_path)
    assert status == inspect_local_operations(config, project_root=tmp_path)
    assert status.database_state == "AVAILABLE"
    assert status.session_id == "paper-local-001"
    assert status.runtime_state == "SHADOW"
    assert status.operator_health == "ATTENTION"
    assert status.incident_count == 1
    assert status.unmatched_reconciliation_count == 1
    assert status.reason_codes == ("INCIDENT_PRESENT", "RECONCILIATION_UNMATCHED")
    assert status.latest_heartbeat_at is not None
    assert status.latest_checkpoint_at is not None
    assert _digest(database) == before


def test_legacy_database_without_operator_snapshot_table_still_shows_session(
    tmp_path: Path,
) -> None:
    database = tmp_path / "webull-sandbox.sqlite"
    _paper_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE paper_operator_snapshots")
    status = inspect_local_operations(load_local_status_config(CONFIG), project_root=tmp_path)
    assert status.database_state == "AVAILABLE"
    assert status.session_id == "paper-local-001"
    assert status.runtime_state == "SHADOW"
    assert status.operator_health == "UNAVAILABLE"
    assert status.reason_codes == ("OPERATOR_SNAPSHOT_MISSING",)


def test_tampered_snapshot_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "webull-sandbox.sqlite"
    _paper_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE paper_operator_snapshots SET payload_json='{}'")
    with pytest.raises(ValueError, match="hash mismatch"):
        inspect_local_operations(load_local_status_config(CONFIG), project_root=tmp_path)


def test_config_rejects_database_escape_and_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["database"] = "../outside.sqlite"
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LocalStatusConfigError, match="database path"):
        load_local_status_config(unsafe)
    raw["database"] = "webull-sandbox.sqlite"
    raw["authority"]["database_write_enabled"] = True
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LocalStatusConfigError, match="authority"):
        load_local_status_config(unsafe)


def test_status_dashboard_cli_renders_local_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _dashboard_root(tmp_path)
    _paper_database(tmp_path / "webull-sandbox.sqlite")
    assert main([
        "desktop",
        "render-status",
        "--config",
        str(CONFIG),
        "--project-root",
        str(tmp_path),
    ]) == 0
    artifact = json.loads(capsys.readouterr().out)
    document = Path(artifact["output_path"]).read_text(encoding="utf-8")
    assert "Latest local paper session" in document
    assert "paper-local-001" in document
    assert "TEST_INCIDENT" not in document
    assert "WEBULL_APP_SECRET" not in document
    assert "<script" not in document
