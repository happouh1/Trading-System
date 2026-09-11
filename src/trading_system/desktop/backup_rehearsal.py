"""Phase 9Q test-only rehearsal of the authorized-backup procedure."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.backup_authorization import (
    BackupAuthorizationAssessment,
    BackupAuthorizationEvidenceState,
    BackupAuthorizationRequest,
)
from trading_system.desktop.backup_manifest import RealDatabaseBackupManifest
from trading_system.serialization import canonical_hash, deterministic_id


class BackupRehearsalConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BackupRehearsalConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class AuthorizedBackupRehearsalResult:
    rehearsal_id: str
    status: str
    request_id: str
    manifest_id: str
    source_revision: str
    source_path: str
    source_hash_before: str
    source_hash_after: str
    backup_hash: str
    restored_hash: str
    logical_snapshot_hash: str
    table_row_counts: tuple[tuple[str, int], ...]
    backup_quick_check: tuple[str, ...]
    restored_quick_check: tuple[str, ...]
    backup_foreign_key_violations: int
    restored_foreign_key_violations: int
    backup_path: str
    restored_path: str
    reused_existing_artifacts: bool
    config_hash: str
    rehearsal_version: str = "9Q.1.0"
    test_only: bool = True
    test_nonce_consumed: bool = True
    test_backup_created: bool = True
    test_restore_executed: bool = True
    real_backup_authorized: bool = False
    production_backup_created: bool = False
    source_database_write_performed: bool = False
    restore_promoted: bool = False
    migration_executed: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.rehearsal_id, self.request_id, self.manifest_id, self.source_path))
            or self.status != "VERIFIED"
            or not self.source_revision.startswith("TEST_ONLY_")
            or any(
                not _sha(value)
                for value in (
                    self.source_hash_before,
                    self.source_hash_after,
                    self.backup_hash,
                    self.restored_hash,
                    self.logical_snapshot_hash,
                    self.config_hash,
                )
            )
            or self.source_hash_before != self.source_hash_after
            or self.table_row_counts != tuple(sorted(self.table_row_counts))
            or self.backup_quick_check != ("ok",)
            or self.restored_quick_check != ("ok",)
            or self.backup_foreign_key_violations
            or self.restored_foreign_key_violations
            or not all((self.backup_path, self.restored_path))
            or self.rehearsal_version != "9Q.1.0"
            or not all(
                (
                    self.test_only,
                    self.test_nonce_consumed,
                    self.test_backup_created,
                    self.test_restore_executed,
                )
            )
            or any(
                (
                    self.real_backup_authorized,
                    self.production_backup_created,
                    self.source_database_write_performed,
                    self.restore_promoted,
                    self.migration_executed,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9Q authorized-backup rehearsal result")


def load_backup_rehearsal_config(path: str | Path) -> BackupRehearsalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "rehearsal_version",
        "mode",
        "authorization_config",
        "allowed_source_root",
        "output_directory",
        "verification",
        "authority",
    }:
        raise BackupRehearsalConfigError("Phase 9Q configuration keys are invalid")
    if (
        raw["rehearsal_version"] != "9Q.1.0"
        or raw["mode"] != "TEST_ONLY_AUTHORIZED_BACKUP_REHEARSAL"
    ):
        raise BackupRehearsalConfigError("Phase 9Q mode is invalid")
    for key in ("authorization_config", "allowed_source_root", "output_directory"):
        if not _relative(raw[key]):
            raise BackupRehearsalConfigError(f"Phase 9Q {key} path is invalid")
    if raw["verification"] != {
        "require_verified_phase9p_evidence": True,
        "require_test_only_revision": True,
        "require_source_hash_match": True,
        "reject_sqlite_sidecars": True,
        "preserve_source_hash": True,
        "sqlite_quick_check": True,
        "foreign_key_check": True,
        "logical_restore_equivalence": True,
        "deterministic_restart": True,
    }:
        raise BackupRehearsalConfigError("Phase 9Q verification controls are invalid")
    authority = raw["authority"]
    expected = {
        "real_database_source_enabled",
        "real_backup_authorized",
        "production_backup_enabled",
        "source_database_write_enabled",
        "restore_promotion_enabled",
        "migration_execution_enabled",
        "process_launch_enabled",
        "network_enabled",
        "credential_loading_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise BackupRehearsalConfigError("Phase 9Q authority must remain test-only")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupRehearsalConfig(MappingProxyType(frozen), canonical_hash(raw))


def rehearse_authorized_backup(
    config: BackupRehearsalConfig,
    *,
    project_root: str | Path,
    source_path: str,
    source_revision: str,
    manifest: RealDatabaseBackupManifest,
    request: BackupAuthorizationRequest,
    assessment: BackupAuthorizationAssessment,
    observed_at: datetime,
) -> AuthorizedBackupRehearsalResult:
    if not source_revision.startswith("TEST_ONLY_"):
        raise ValueError("Phase 9Q source revision must begin with TEST_ONLY_")
    if not _utc(observed_at):
        raise ValueError("Phase 9Q observation time must be UTC")
    if (
        assessment.state
        is not BackupAuthorizationEvidenceState.BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED
    ):
        raise ValueError("Phase 9Q requires verified Phase 9P evidence")
    if (
        assessment.request_id != request.request_id
        or assessment.request_hash != request.request_hash
        or assessment.config_hash != request.config_hash
    ):
        raise ValueError("Phase 9Q assessment does not match the request")
    if not request.valid_from <= observed_at < request.valid_until:
        raise ValueError("Phase 9Q observation is outside the authorization window")
    if (
        request.manifest_id != manifest.manifest_id
        or request.manifest_hash != canonical_hash(manifest)
        or request.preflight_id != manifest.preflight_id
        or request.preflight_hash != manifest.preflight_hash
        or request.source_hash != manifest.source_hash
        or request.target_path != manifest.target_path
        or request.execution_component_id != manifest.execution_component_id
    ):
        raise ValueError("Phase 9Q request does not match the manifest")
    root = Path(project_root).resolve()
    allowed = _directory(root, config.values["allowed_source_root"])
    source = _file(root, source_path)
    if allowed != source.parent and allowed not in source.parents:
        raise ValueError("Phase 9Q source must be inside the test-only fixture directory")
    sidecars = tuple(Path(f"{source}{suffix}") for suffix in ("-journal", "-shm", "-wal"))
    if any(path.exists() for path in sidecars):
        raise ValueError("Phase 9Q source has SQLite sidecars")
    source_hash = _hash_file(source)
    if source_hash != request.source_hash:
        raise ValueError("Phase 9Q source hash does not match reviewed evidence")
    output = _directory(root, config.values["output_directory"])
    if output == source.parent or output in source.parents:
        raise ValueError("Phase 9Q output cannot contain the source fixture")
    rehearsal_key = (
        source_path,
        source_revision,
        source_hash,
        request.request_id,
        request.request_hash,
        assessment.assessment_id,
        observed_at,
        config.config_hash,
    )
    rehearsal_id = deterministic_id("authorized_backup_rehearsal", rehearsal_key)
    output.mkdir(parents=True, exist_ok=True)
    target = output / rehearsal_id
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=output))
    try:
        backup = stage / "backup.sqlite"
        restored = stage / "restored.sqlite"
        _sqlite_backup(source, backup)
        _sqlite_backup(backup, restored)
        result = _verified_result(
            config=config,
            rehearsal_id=rehearsal_id,
            request=request,
            manifest=manifest,
            source=source,
            source_path=source_path,
            source_revision=source_revision,
            source_hash=source_hash,
            backup=backup,
            restored=restored,
            target=target,
            root=root,
            reused=target.exists(),
        )
        if target.exists():
            _verify_existing(target, backup, restored)
        else:
            stage.replace(target)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _verified_result(
    *,
    config: BackupRehearsalConfig,
    rehearsal_id: str,
    request: BackupAuthorizationRequest,
    manifest: RealDatabaseBackupManifest,
    source: Path,
    source_path: str,
    source_revision: str,
    source_hash: str,
    backup: Path,
    restored: Path,
    target: Path,
    root: Path,
    reused: bool,
) -> AuthorizedBackupRehearsalResult:
    source_after = _hash_file(source)
    if source_after != source_hash:
        raise ValueError("Phase 9Q source changed during rehearsal")
    source_snapshot = _logical_snapshot(source)
    backup_snapshot = _logical_snapshot(backup)
    restored_snapshot = _logical_snapshot(restored)
    if source_snapshot != backup_snapshot or source_snapshot != restored_snapshot:
        raise ValueError("Phase 9Q logical restore verification failed")
    backup_quick, backup_foreign = _sqlite_checks(backup)
    restored_quick, restored_foreign = _sqlite_checks(restored)
    if backup_quick != ("ok",) or restored_quick != ("ok",):
        raise ValueError("Phase 9Q SQLite integrity verification failed")
    if backup_foreign or restored_foreign:
        raise ValueError("Phase 9Q foreign-key verification failed")
    relative_target = target.relative_to(root)
    rows = _row_counts(source)
    logical_hash = canonical_hash(source_snapshot)
    identity = (
        rehearsal_id,
        request.request_id,
        manifest.manifest_id,
        source_revision,
        source_path,
        source_hash,
        _hash_file(backup),
        _hash_file(restored),
        logical_hash,
        rows,
        config.config_hash,
    )
    return AuthorizedBackupRehearsalResult(
        deterministic_id("authorized_backup_rehearsal_result", identity),
        "VERIFIED",
        request.request_id,
        manifest.manifest_id,
        source_revision,
        source_path,
        source_hash,
        source_after,
        _hash_file(backup),
        _hash_file(restored),
        logical_hash,
        rows,
        backup_quick,
        restored_quick,
        backup_foreign,
        restored_foreign,
        (relative_target / "backup.sqlite").as_posix(),
        (relative_target / "restored.sqlite").as_posix(),
        reused,
        config.config_hash,
    )


def _sqlite_backup(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _logical_snapshot(path: Path) -> tuple[tuple[str, str, tuple[tuple[str, ...], ...]], ...]:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        tables = tuple(
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                "SELECT name,sql FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        result = []
        for name, sql in tables:
            quoted = name.replace('"', '""')
            rows = tuple(
                sorted(
                    tuple(repr(value) for value in row)
                    for row in connection.execute(f'SELECT * FROM "{quoted}"')
                )
            )
            result.append((name, sql, rows))
        return tuple(result)
    finally:
        connection.close()


def _row_counts(path: Path) -> tuple[tuple[str, int], ...]:
    return tuple((name, len(rows)) for name, _, rows in _logical_snapshot(path))


def _sqlite_checks(path: Path) -> tuple[tuple[str, ...], int]:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        foreign = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
        return quick, foreign
    finally:
        connection.close()


def _verify_existing(target: Path, backup: Path, restored: Path) -> None:
    if not target.is_dir() or target.is_symlink():
        raise ValueError("Phase 9Q existing rehearsal target is invalid")
    for name, staged in (("backup.sqlite", backup), ("restored.sqlite", restored)):
        existing = target / name
        if (
            not existing.is_file()
            or existing.is_symlink()
            or _hash_file(existing) != _hash_file(staged)
        ):
            raise ValueError("Phase 9Q existing rehearsal artifact conflicts")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _directory(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not _relative(value):
        raise BackupRehearsalConfigError("Phase 9Q directory path is invalid")
    result = (root / Path(*PurePosixPath(value).parts)).resolve()
    if root not in result.parents:
        raise ValueError("Phase 9Q directory escapes project root")
    return result


def _file(root: Path, value: str) -> Path:
    if not _relative(value):
        raise ValueError("Phase 9Q source path must be contained and relative")
    raw = root / Path(*PurePosixPath(value).parts)
    result = raw.resolve()
    if root not in result.parents or not raw.is_file() or raw.is_symlink():
        raise ValueError("Phase 9Q source must be an existing regular file")
    return raw


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path != PurePosixPath(".")


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
