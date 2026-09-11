from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop import (
    AuthorizedBackupRehearsalResult,
    BackupAuthorizationAssessment,
    BackupAuthorizationEvidenceState,
    BackupAuthorizationRequest,
    RealDatabaseBackupManifest,
    RealDatabaseBackupManifestState,
    load_backup_rehearsal_config,
    rehearse_authorized_backup,
)
from trading_system.desktop.backup_rehearsal import BackupRehearsalConfigError
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9q.v1.yaml"
NOW = datetime(2026, 9, 10, 17, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _source(tmp_path: Path) -> tuple[Path, str, str]:
    relative = "fixtures/backup-authorization-rehearsal/legacy.sqlite"
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path, relative, _hash(path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL "
            "REFERENCES parent(id))"
        )
        connection.execute("INSERT INTO parent VALUES (1, 'test-only')")
        connection.execute("INSERT INTO child VALUES (1, 1)")
        connection.commit()
    finally:
        connection.close()
    return path, relative, _hash(path)


def _evidence(
    source_path: str, source_hash: str
) -> tuple[
    RealDatabaseBackupManifest,
    BackupAuthorizationRequest,
    BackupAuthorizationAssessment,
]:
    target = f"backups/operator-db/legacy-{source_hash[7:23]}.sqlite"
    manifest = RealDatabaseBackupManifest(
        "manifest-9o-test",
        RealDatabaseBackupManifestState.READY_FOR_AUTHORIZATION_REVIEW,
        NOW,
        "preflight-9n-test",
        HASH_A,
        source_path,
        source_hash,
        16384,
        target,
        "SQLITE_BACKUP_API_TO_EXCLUSIVE_NEW_FILE",
        ("SOURCE_HASH_BEFORE", "SQLITE_BACKUP_API", "RESTORE_TEST"),
        HASH_A,
        HASH_B,
        HASH_C,
        "test-only-backup-component",
        (),
        HASH_A,
    )
    request = BackupAuthorizationRequest(
        "request-9p-test",
        manifest.manifest_id,
        canonical_hash(manifest),
        manifest.preflight_id,
        manifest.preflight_hash,
        source_hash,
        target,
        manifest.execution_component_id,
        "test-only-nonce",
        NOW,
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=30),
        ("OPERATIONS_REVIEWER", "SECURITY_REVIEWER"),
        HASH_B,
        HASH_C,
    )
    assessment = BackupAuthorizationAssessment(
        "assessment-9p-test",
        request.request_id,
        NOW + timedelta(minutes=5),
        BackupAuthorizationEvidenceState.BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED,
        request.required_review_roles,
        (),
        request.request_hash,
        request.config_hash,
    )
    return manifest, request, assessment


def _run(tmp_path: Path) -> AuthorizedBackupRehearsalResult:
    source, relative, source_hash = _source(tmp_path)
    manifest, request, assessment = _evidence(relative, source_hash)
    before = source.read_bytes()
    result = rehearse_authorized_backup(
        load_backup_rehearsal_config(CONFIG),
        project_root=tmp_path,
        source_path=relative,
        source_revision="TEST_ONLY_AUTHORIZED_BACKUP_V1",
        manifest=manifest,
        request=request,
        assessment=assessment,
        observed_at=NOW + timedelta(minutes=10),
    )
    assert source.read_bytes() == before
    return result


def test_verified_rehearsal_creates_only_test_artifacts(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.status == "VERIFIED"
    assert result.backup_quick_check == ("ok",)
    assert result.restored_quick_check == ("ok",)
    assert result.table_row_counts == (("child", 1), ("parent", 1))
    assert (tmp_path / result.backup_path).is_file()
    assert (tmp_path / result.restored_path).is_file()
    assert result.test_backup_created
    assert not result.production_backup_created
    assert not result.source_database_write_performed
    assert not result.network_used


def test_real_operator_database_and_non_test_revision_are_rejected(tmp_path: Path) -> None:
    source, relative, source_hash = _source(tmp_path)
    manifest, request, assessment = _evidence(relative, source_hash)
    operator_database = tmp_path / "webull-sandbox.sqlite"
    operator_database.write_bytes(source.read_bytes())
    kwargs = {
        "config": load_backup_rehearsal_config(CONFIG),
        "project_root": tmp_path,
        "source_revision": "TEST_ONLY_V1",
        "manifest": manifest,
        "request": request,
        "assessment": assessment,
        "observed_at": NOW + timedelta(minutes=10),
    }
    with pytest.raises(ValueError, match="fixture"):
        rehearse_authorized_backup(source_path="webull-sandbox.sqlite", **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="TEST_ONLY"):
        rehearse_authorized_backup(
            source_path=relative,
            **(kwargs | {"source_revision": "PRODUCTION"}),  # type: ignore[arg-type]
        )


def test_sidecars_are_rejected_before_sqlite_open(tmp_path: Path) -> None:
    source, relative, source_hash = _source(tmp_path)
    manifest, request, assessment = _evidence(relative, source_hash)
    sidecar = Path(f"{source}-wal")
    sidecar.write_bytes(b"operator-owned-test-sidecar")
    with pytest.raises(ValueError, match="sidecars"):
        rehearse_authorized_backup(
            load_backup_rehearsal_config(CONFIG),
            project_root=tmp_path,
            source_path=relative,
            source_revision="TEST_ONLY_V1",
            manifest=manifest,
            request=request,
            assessment=assessment,
            observed_at=NOW + timedelta(minutes=10),
        )
    assert tuple(path.name for path in source.parent.glob("legacy.sqlite-*")) == (
        "legacy.sqlite-wal",
    )


def test_mismatched_or_expired_evidence_is_rejected(tmp_path: Path) -> None:
    _, relative, source_hash = _source(tmp_path)
    manifest, request, assessment = _evidence(relative, source_hash)
    with pytest.raises(ValueError, match="assessment"):
        rehearse_authorized_backup(
            load_backup_rehearsal_config(CONFIG),
            project_root=tmp_path,
            source_path=relative,
            source_revision="TEST_ONLY_V1",
            manifest=manifest,
            request=request,
            assessment=replace(assessment, request_hash=HASH_A),
            observed_at=NOW + timedelta(minutes=10),
        )
    with pytest.raises(ValueError, match="window"):
        rehearse_authorized_backup(
            load_backup_rehearsal_config(CONFIG),
            project_root=tmp_path,
            source_path=relative,
            source_revision="TEST_ONLY_V1",
            manifest=manifest,
            request=request,
            assessment=assessment,
            observed_at=NOW + timedelta(minutes=30),
        )


def test_restart_reuses_only_identical_artifacts(tmp_path: Path) -> None:
    first = _run(tmp_path)
    source = tmp_path / "fixtures/backup-authorization-rehearsal/legacy.sqlite"
    _, relative, source_hash = source, source.relative_to(tmp_path).as_posix(), _hash(source)
    manifest, request, assessment = _evidence(relative, source_hash)
    second = rehearse_authorized_backup(
        load_backup_rehearsal_config(CONFIG),
        project_root=tmp_path,
        source_path=relative,
        source_revision="TEST_ONLY_AUTHORIZED_BACKUP_V1",
        manifest=manifest,
        request=request,
        assessment=assessment,
        observed_at=NOW + timedelta(minutes=10),
    )
    assert second.reused_existing_artifacts
    assert first.rehearsal_id == second.rehearsal_id
    assert first.backup_hash == second.backup_hash


def test_existing_artifact_conflict_fails_closed(tmp_path: Path) -> None:
    first = _run(tmp_path)
    (tmp_path / first.backup_path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="conflicts"):
        _run(tmp_path)


def test_config_weakening_and_result_serialization(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["real_database_source_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupRehearsalConfigError, match="test-only"):
        load_backup_rehearsal_config(invalid)
    result = _run(tmp_path)
    assert canonical_json(result) == canonical_json(result)


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
