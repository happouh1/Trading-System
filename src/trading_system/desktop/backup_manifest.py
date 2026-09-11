"""Phase 9O offline manifest for a future real-database backup."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.backup_preflight import (
    RealDatabaseBackupPreflight,
    RealDatabaseBackupPreflightState,
)
from trading_system.serialization import canonical_hash, deterministic_id


class BackupManifestConfigError(ValueError):
    pass


class RealDatabaseBackupManifestState(StrEnum):
    READY_FOR_AUTHORIZATION_REVIEW = "READY_FOR_AUTHORIZATION_REVIEW"
    EXISTING_BACKUP_REVIEW_REQUIRED = "EXISTING_BACKUP_REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BackupManifestConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RealDatabaseBackupManifest:
    manifest_id: str
    state: RealDatabaseBackupManifestState
    created_at: datetime
    preflight_id: str
    preflight_hash: str
    source_path: str
    source_hash: str | None
    source_bytes: int | None
    target_path: str | None
    backup_method: str
    verification_steps: tuple[str, ...]
    encryption_policy_hash: str
    retention_policy_hash: str
    restore_test_policy_hash: str
    execution_component_id: str
    blocker_codes: tuple[str, ...]
    config_hash: str
    manifest_version: str = "9O.1.0"
    backup_authorized: bool = False
    directory_created: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    migration_executed: bool = False
    restore_executed: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        expected = (
            RealDatabaseBackupManifestState.BLOCKED
            if self.blocker_codes
            else self.state
        )
        if (
            not all(
                (
                    self.manifest_id,
                    self.preflight_id,
                    self.source_path,
                    self.backup_method,
                    self.execution_component_id,
                )
            )
            or not _utc(self.created_at)
            or any(
                not _sha(value)
                for value in (
                    self.preflight_hash,
                    self.encryption_policy_hash,
                    self.retention_policy_hash,
                    self.restore_test_policy_hash,
                    self.config_hash,
                )
            )
            or (self.source_hash is not None and not _sha(self.source_hash))
            or (self.source_bytes is not None and self.source_bytes < 0)
            or self.blocker_codes != tuple(sorted(set(self.blocker_codes)))
            or not self.verification_steps
            or self.state is not expected
            or self.manifest_version != "9O.1.0"
            or any(
                (
                    self.backup_authorized,
                    self.directory_created,
                    self.backup_created,
                    self.database_write_performed,
                    self.migration_executed,
                    self.restore_executed,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9O real-database backup manifest")


def load_backup_manifest_config(path: str | Path) -> BackupManifestConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "manifest_version",
        "mode",
        "backup_preflight_config",
        "backup_method",
        "verification_steps",
        "policy",
        "authority",
    }:
        raise BackupManifestConfigError("Phase 9O configuration keys are invalid")
    if (
        raw["manifest_version"] != "9O.1.0"
        or raw["mode"] != "OFFLINE_REAL_DATABASE_BACKUP_MANIFEST"
        or not _relative(raw["backup_preflight_config"])
        or raw["backup_method"] != "SQLITE_BACKUP_API_TO_EXCLUSIVE_NEW_FILE"
        or raw["verification_steps"]
        != [
            "SOURCE_HASH_BEFORE",
            "SQLITE_BACKUP_API",
            "SOURCE_HASH_AFTER",
            "TARGET_QUICK_CHECK",
            "TARGET_FOREIGN_KEY_CHECK",
            "TARGET_HASH_MATCH",
            "RESTORE_TEST",
        ]
    ):
        raise BackupManifestConfigError("Phase 9O mode or procedure is invalid")
    if raw["policy"] != {
        "require_phase9n_preflight": True,
        "require_content_addressed_target": True,
        "require_encryption_policy_hash": True,
        "require_retention_policy_hash": True,
        "require_restore_test_policy_hash": True,
        "execution_component_operator_supplied": True,
        "existing_backup_requires_review": True,
        "blocked_preflight_propagates": True,
    }:
        raise BackupManifestConfigError("Phase 9O policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "backup_authorization_enabled",
        "directory_creation_enabled",
        "backup_creation_enabled",
        "database_write_enabled",
        "migration_execution_enabled",
        "restore_execution_enabled",
        "process_launch_enabled",
        "network_enabled",
        "credential_loading_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise BackupManifestConfigError("Phase 9O authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value))
        if isinstance(value, dict)
        else tuple(value)
        if isinstance(value, list)
        else value
        for key, value in raw.items()
    }
    return BackupManifestConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_real_database_backup_manifest(
    config: BackupManifestConfig,
    *,
    preflight: RealDatabaseBackupPreflight,
    encryption_policy_hash: str,
    retention_policy_hash: str,
    restore_test_policy_hash: str,
    execution_component_id: str,
    created_at: datetime,
) -> RealDatabaseBackupManifest:
    if not _utc(created_at):
        raise ValueError("Phase 9O creation time must be UTC")
    if any(
        not _sha(value)
        for value in (
            encryption_policy_hash,
            retention_policy_hash,
            restore_test_policy_hash,
        )
    ):
        raise ValueError("Phase 9O policy references must be SHA-256 identities")
    if not execution_component_id.strip():
        raise ValueError("Phase 9O execution component identity is required")
    backup_method = config.values["backup_method"]
    steps_value = config.values["verification_steps"]
    if not isinstance(backup_method, str) or not isinstance(steps_value, tuple):
        raise TypeError("validated Phase 9O procedure has invalid types")
    steps = tuple(str(value) for value in steps_value)
    blockers = set(preflight.blocker_codes)
    if preflight.source_hash is None:
        blockers.add("SOURCE_HASH_UNAVAILABLE")
    if preflight.target_path is None:
        blockers.add("TARGET_PATH_UNAVAILABLE")
    elif preflight.source_hash is not None:
        expected_suffix = f"-{preflight.source_hash[7:23]}.sqlite"
        if not preflight.target_path.endswith(expected_suffix):
            blockers.add("TARGET_NOT_CONTENT_ADDRESSED")
    if preflight.state is RealDatabaseBackupPreflightState.BLOCKED:
        blockers.add("PHASE9N_PREFLIGHT_BLOCKED")
    blocker_codes = tuple(sorted(blockers))
    if blocker_codes:
        state = RealDatabaseBackupManifestState.BLOCKED
    elif preflight.state is RealDatabaseBackupPreflightState.BACKUP_ALREADY_PRESENT:
        state = RealDatabaseBackupManifestState.EXISTING_BACKUP_REVIEW_REQUIRED
    else:
        state = RealDatabaseBackupManifestState.READY_FOR_AUTHORIZATION_REVIEW
    preflight_hash = canonical_hash(preflight)
    identity = (
        state,
        created_at,
        preflight.preflight_id,
        preflight_hash,
        preflight.source_path,
        preflight.source_hash,
        preflight.source_bytes,
        preflight.target_path,
        backup_method,
        steps,
        encryption_policy_hash,
        retention_policy_hash,
        restore_test_policy_hash,
        execution_component_id,
        blocker_codes,
        config.config_hash,
    )
    return RealDatabaseBackupManifest(
        deterministic_id("real_database_backup_manifest", identity),
        state,
        created_at,
        preflight.preflight_id,
        preflight_hash,
        preflight.source_path,
        preflight.source_hash,
        preflight.source_bytes,
        preflight.target_path,
        backup_method,
        steps,
        encryption_policy_hash,
        retention_policy_hash,
        restore_test_policy_hash,
        execution_component_id,
        blocker_codes,
        config.config_hash,
    )


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
