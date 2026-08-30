"""Contained SQLite backup and isolated restore verification for Phase 5E."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from trading_system.operations.resilience_config import OperationsResilienceConfig
from trading_system.operations.resilience_contracts import BackupManifest, RestoreVerification
from trading_system.operations.resilience_registry import OperationsResilienceRegistry
from trading_system.serialization import deterministic_id


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _contained(root: Path, relative: str | PurePosixPath, *, must_exist: bool) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value == PurePosixPath("."):
        raise ValueError("resilience path must be a contained relative path")
    result = (root / Path(*value.parts)).resolve()
    if root != result and root not in result.parents:
        raise ValueError("resilience path escapes the configured workspace")
    if must_exist and (not result.is_file() or result.is_symlink()):
        raise ValueError("resilience source must be an existing regular file")
    return result


def _sqlite_checks(path: Path) -> tuple[tuple[str, ...], int]:
    uri = path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        quick = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
        foreign = sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))
        return quick, foreign
    finally:
        connection.close()


class OperationsResilienceService:
    def __init__(
        self,
        config: OperationsResilienceConfig,
        registry: OperationsResilienceRegistry,
    ) -> None:
        self.config = config
        self.registry = registry

    def create_backup(
        self,
        *,
        source_path: str,
        known_at: datetime,
        source_revision: str,
    ) -> BackupManifest:
        if not source_revision:
            raise ValueError("backup source revision is required")
        source = _contained(self.config.workspace_root, source_path, must_exist=True)
        backup_root = _contained(
            self.config.workspace_root, self.config.backup_directory, must_exist=False
        )
        restore_root = _contained(
            self.config.workspace_root, self.config.restore_directory, must_exist=False
        )
        if backup_root == source or backup_root in source.parents:
            raise ValueError("backup source cannot be inside the backup directory")
        if restore_root == source or restore_root in source.parents:
            raise ValueError("backup source cannot be inside the restore directory")
        backup_root.mkdir(parents=True, exist_ok=True)
        handle, staging_name = tempfile.mkstemp(
            prefix="sqlite-backup-", suffix=".tmp", dir=backup_root
        )
        os.close(handle)
        Path(staging_name).unlink()
        staging = Path(staging_name)
        try:
            source_connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            destination = sqlite3.connect(staging)
            try:
                source_connection.backup(destination)
            finally:
                destination.close()
                source_connection.close()
            quick, foreign = _sqlite_checks(staging)
            if quick != ("ok",) or foreign:
                raise ValueError("backup artifact failed SQLite integrity verification")
            artifact_hash = _hash_file(staging)
            artifact = backup_root / f"{artifact_hash[7:]}.sqlite"
            if artifact.exists():
                if not artifact.is_file() or artifact.is_symlink():
                    raise ValueError("content-addressed backup path is not a regular file")
                if _hash_file(artifact) != artifact_hash:
                    raise ValueError("content-addressed backup path has conflicting bytes")
                staging.unlink()
            else:
                staging.replace(artifact)
            relative_artifact = artifact.relative_to(self.config.workspace_root).as_posix()
            relative_source = source.relative_to(self.config.workspace_root).as_posix()
            manifest = BackupManifest.create(
                known_at=known_at,
                source_path=relative_source,
                artifact_path=relative_artifact,
                artifact_hash=artifact_hash,
                artifact_bytes=artifact.stat().st_size,
                source_revision=source_revision,
                config=self.config,
            )
            self.registry.insert_backup(manifest)
            return manifest
        finally:
            if staging.exists():
                staging.unlink()

    def verify_restore(self, *, backup_id: str, known_at: datetime) -> RestoreVerification:
        manifest = self.registry.backup(backup_id)
        if known_at < manifest.known_at:
            raise ValueError("restore verification cannot predate its backup")
        artifact = _contained(self.config.workspace_root, manifest.artifact_path, must_exist=True)
        actual_artifact_hash = _hash_file(artifact)
        if actual_artifact_hash != manifest.artifact_hash:
            raise ValueError("backup artifact hash mismatch")
        restore_root = _contained(
            self.config.workspace_root, self.config.restore_directory, must_exist=False
        )
        restore_root.mkdir(parents=True, exist_ok=True)
        restore_name = deterministic_id(
            "operations_restore_artifact",
            (backup_id, known_at, self.config.config_hash),
        )
        restored = restore_root / f"{restore_name}.sqlite"
        if restored.exists():
            if not restored.is_file() or restored.is_symlink():
                raise ValueError("existing restore drill is not a regular file")
            if _hash_file(restored) != manifest.artifact_hash:
                raise ValueError("existing restore drill has conflicting bytes")
        else:
            shutil.copyfile(artifact, restored)
        quick, foreign = _sqlite_checks(restored)
        actual_hash = _hash_file(restored)
        verification = RestoreVerification.create(
            backup_id=backup_id,
            known_at=known_at,
            restored_path=restored.relative_to(self.config.workspace_root).as_posix(),
            expected_hash=manifest.artifact_hash,
            actual_hash=actual_hash,
            quick_check=quick,
            foreign_key_violations=foreign,
            config=self.config,
        )
        self.registry.insert_verification(verification)
        if verification.status.value != "VERIFIED":
            raise ValueError("restored database failed verification")
        return verification
