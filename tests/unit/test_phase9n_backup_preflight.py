from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from trading_system.desktop import (
    DatabaseUpgradeReviewAssessment,
    DatabaseUpgradeReviewRequest,
    DatabaseUpgradeReviewState,
    RealDatabaseBackupPreflight,
    RealDatabaseBackupPreflightState,
    assess_real_database_backup_preflight,
    load_backup_preflight_config,
)
from trading_system.desktop.backup_preflight import BackupPreflightConfigError
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9n.v1.yaml"
NOW = datetime(2026, 9, 10, 14, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in (
        "desktop.phase9i.v1.yaml",
        "desktop.phase9j.v1.yaml",
        "desktop.phase9k.v1.yaml",
    ):
        shutil.copyfile(ROOT / "config" / name, config_dir / name)
    database = tmp_path / "webull-sandbox.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO evidence(value) VALUES ('unchanged')")
        connection.commit()
    finally:
        connection.close()
    destination = tmp_path / "backups" / "operator-db"
    destination.mkdir(parents=True)
    return database, _hash(database)


def _evidence(source_hash: str) -> tuple[
    DatabaseUpgradeReviewRequest, DatabaseUpgradeReviewAssessment
]:
    request = DatabaseUpgradeReviewRequest(
        "request-9n",
        "plan-9k",
        HASH_A,
        "rehearsal-9l",
        HASH_B,
        source_hash,
        HASH_A,
        HASH_B,
        HASH_A,
        NOW - timedelta(hours=1),
        NOW - timedelta(minutes=30),
        NOW + timedelta(minutes=30),
        ("OPERATIONS_REVIEWER", "SECURITY_REVIEWER"),
        HASH_B,
        HASH_A,
    )
    assessment = DatabaseUpgradeReviewAssessment(
        "assessment-9m",
        request.request_id,
        NOW - timedelta(minutes=15),
        DatabaseUpgradeReviewState.REVIEW_EVIDENCE_VERIFIED,
        request.required_review_roles,
        (),
        request.request_hash,
        request.config_hash,
    )
    return request, assessment


def _assess(
    tmp_path: Path,
    request: DatabaseUpgradeReviewRequest,
    assessment: DatabaseUpgradeReviewAssessment,
    **changes: object,
) -> RealDatabaseBackupPreflight:
    values: dict[str, Any] = {
        "project_root": tmp_path,
        "request": request,
        "assessment": assessment,
        "approved_destination_root": "backups",
        "destination_path": "backups/operator-db",
        "minimum_free_bytes": 1_048_576,
        "quiescence_evidence_hash": HASH_B,
        "observed_at": NOW,
    }
    values.update(changes)
    return assess_real_database_backup_preflight(load_backup_preflight_config(CONFIG), **values)


def test_ready_preflight_is_read_only_and_bound_to_configured_source(tmp_path: Path) -> None:
    database, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    before = database.read_bytes()
    result = _assess(tmp_path, request, assessment)
    assert result.state is RealDatabaseBackupPreflightState.READY_FOR_BACKUP_REVIEW
    assert result.quick_check == ("ok",)
    assert result.foreign_key_violation_count == 0
    assert result.source_path == "webull-sandbox.sqlite"
    assert result.target_path == f"backups/operator-db/webull-sandbox-{source_hash[7:23]}.sqlite"
    assert not result.backup_created
    assert not result.database_write_performed
    assert not result.network_used
    assert database.read_bytes() == before
    assert tuple((tmp_path / "backups/operator-db").iterdir()) == ()


def test_sqlite_sidecar_blocks_without_modifying_source(tmp_path: Path) -> None:
    database, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    sidecar = Path(f"{database}-wal")
    sidecar.write_bytes(b"operator-owned")
    result = _assess(tmp_path, request, assessment)
    assert result.state is RealDatabaseBackupPreflightState.BLOCKED
    assert result.blocker_codes == ("SQLITE_SIDECARS_PRESENT",)
    assert result.sidecar_paths == ("webull-sandbox.sqlite-wal",)
    assert sidecar.read_bytes() == b"operator-owned"


def test_review_hash_and_maintenance_window_fail_closed(tmp_path: Path) -> None:
    _, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    result = _assess(
        tmp_path,
        replace(request, source_hash=HASH_A),
        replace(assessment, request_hash=HASH_A),
        observed_at=NOW + timedelta(hours=1),
    )
    assert result.state is RealDatabaseBackupPreflightState.BLOCKED
    assert set(result.blocker_codes) == {
        "OUTSIDE_MAINTENANCE_WINDOW",
        "PHASE9M_EVIDENCE_MISMATCH",
        "SOURCE_HASH_MISMATCH",
    }


def test_destination_absence_and_capacity_policy_do_not_create_paths(tmp_path: Path) -> None:
    database, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    missing = tmp_path / "backups/missing"
    result = _assess(
        tmp_path,
        request,
        assessment,
        destination_path="backups/missing",
        minimum_free_bytes=database.stat().st_size - 1,
    )
    assert result.state is RealDatabaseBackupPreflightState.BLOCKED
    assert "DESTINATION_UNAVAILABLE" in result.blocker_codes
    assert "MINIMUM_FREE_BYTES_BELOW_SOURCE_SIZE" in result.blocker_codes
    assert not missing.exists()


def test_existing_identical_target_is_distinct_from_conflict(tmp_path: Path) -> None:
    database, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    target = tmp_path / "backups/operator-db" / f"webull-sandbox-{source_hash[7:23]}.sqlite"
    shutil.copyfile(database, target)
    present = _assess(tmp_path, request, assessment)
    assert present.state is RealDatabaseBackupPreflightState.BACKUP_ALREADY_PRESENT
    assert present.target_already_present
    target.write_bytes(b"conflicting artifact")
    conflict = _assess(tmp_path, request, assessment)
    assert conflict.state is RealDatabaseBackupPreflightState.BLOCKED
    assert conflict.blocker_codes == ("TARGET_CONFLICT",)


def test_config_and_paths_fail_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["backup_creation_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupPreflightConfigError, match="authority"):
        load_backup_preflight_config(invalid)
    database, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    with pytest.raises(ValueError, match="canonical"):
        _assess(
            tmp_path,
            request,
            assessment,
            destination_path="backups/../operator-db",
        )
    assert database.is_file()


def test_preflight_is_deterministic_and_canonical(tmp_path: Path) -> None:
    _, source_hash = _workspace(tmp_path)
    request, assessment = _evidence(source_hash)
    first = _assess(tmp_path, request, assessment)
    second = _assess(tmp_path, request, assessment)
    assert first == second
    assert canonical_json(first) == canonical_json(second)


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
