"""Phase 9N read-only preflight for a future real-database backup."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.local_status import load_local_status_config
from trading_system.desktop.readiness import load_launch_readiness_config
from trading_system.desktop.upgrade_authorization import (
    DatabaseUpgradeReviewAssessment,
    DatabaseUpgradeReviewRequest,
    DatabaseUpgradeReviewState,
)
from trading_system.desktop.upgrade_plan import load_upgrade_plan_config
from trading_system.serialization import canonical_hash, deterministic_id


class BackupPreflightConfigError(ValueError):
    pass


class RealDatabaseBackupPreflightState(StrEnum):
    READY_FOR_BACKUP_REVIEW = "READY_FOR_BACKUP_REVIEW"
    BACKUP_ALREADY_PRESENT = "BACKUP_ALREADY_PRESENT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BackupPreflightConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RealDatabaseBackupPreflight:
    preflight_id: str
    state: RealDatabaseBackupPreflightState
    observed_at: datetime
    request_id: str
    assessment_id: str
    source_path: str
    source_hash: str | None
    source_bytes: int | None
    destination_root: str
    destination_path: str
    target_path: str | None
    minimum_free_bytes: int
    capacity_satisfied: bool
    quick_check: tuple[str, ...]
    foreign_key_violation_count: int | None
    sidecar_paths: tuple[str, ...]
    quiescence_evidence_hash: str
    target_already_present: bool
    blocker_codes: tuple[str, ...]
    config_hash: str
    preflight_version: str = "9N.1.0"
    directory_created: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    migration_executed: bool = False
    restore_promoted: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        expected_state = (
            RealDatabaseBackupPreflightState.BLOCKED
            if self.blocker_codes
            else RealDatabaseBackupPreflightState.BACKUP_ALREADY_PRESENT
            if self.target_already_present
            else RealDatabaseBackupPreflightState.READY_FOR_BACKUP_REVIEW
        )
        if (
            not all((self.preflight_id, self.request_id, self.assessment_id))
            or not _utc(self.observed_at)
            or (self.source_bytes is not None and self.source_bytes < 0)
            or self.minimum_free_bytes <= 0
            or self.blocker_codes != tuple(sorted(set(self.blocker_codes)))
            or self.sidecar_paths != tuple(sorted(set(self.sidecar_paths)))
            or self.state is not expected_state
            or not _sha(self.quiescence_evidence_hash)
            or not _sha(self.config_hash)
            or self.preflight_version != "9N.1.0"
            or any(
                (
                    self.directory_created,
                    self.backup_created,
                    self.database_write_performed,
                    self.migration_executed,
                    self.restore_promoted,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9N real-database backup preflight")


def load_backup_preflight_config(path: str | Path) -> BackupPreflightConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "preflight_version",
        "mode",
        "upgrade_plan_config",
        "policy",
        "authority",
    }:
        raise BackupPreflightConfigError("Phase 9N configuration keys are invalid")
    if (
        raw["preflight_version"] != "9N.1.0"
        or raw["mode"] != "READ_ONLY_REAL_DATABASE_BACKUP_PREFLIGHT"
        or not _relative(raw["upgrade_plan_config"])
    ):
        raise BackupPreflightConfigError("Phase 9N mode or plan path is invalid")
    if raw["policy"] != {
        "require_phase9m_review_evidence_verified": True,
        "require_source_hash_match": True,
        "require_maintenance_window": True,
        "require_quiescence_evidence_hash": True,
        "reject_sqlite_sidecars": True,
        "require_sqlite_quick_check": True,
        "require_zero_foreign_key_violations": True,
        "destination_root_operator_supplied": True,
        "destination_must_exist": True,
        "destination_must_be_directory": True,
        "destination_symlink_rejected": True,
        "minimum_free_bytes_operator_supplied": True,
        "target_conflicts_rejected": True,
    }:
        raise BackupPreflightConfigError("Phase 9N policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "directory_creation_enabled",
        "backup_creation_enabled",
        "database_write_enabled",
        "migration_execution_enabled",
        "restore_promotion_enabled",
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
        raise BackupPreflightConfigError("Phase 9N authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupPreflightConfig(MappingProxyType(frozen), canonical_hash(raw))


def assess_real_database_backup_preflight(
    config: BackupPreflightConfig,
    *,
    project_root: str | Path,
    request: DatabaseUpgradeReviewRequest,
    assessment: DatabaseUpgradeReviewAssessment,
    approved_destination_root: str,
    destination_path: str,
    minimum_free_bytes: int,
    quiescence_evidence_hash: str,
    observed_at: datetime,
) -> RealDatabaseBackupPreflight:
    if not _utc(observed_at):
        raise ValueError("Phase 9N observation time must be UTC")
    if not _sha(quiescence_evidence_hash):
        raise ValueError("Phase 9N quiescence evidence must be a SHA-256 identity")
    if isinstance(minimum_free_bytes, bool) or minimum_free_bytes <= 0:
        raise ValueError("Phase 9N minimum free bytes must be a positive integer")
    root = Path(project_root).resolve()
    source = _configured_database(config, root)
    destination_root = _operator_path(root, approved_destination_root)
    destination = _operator_path(root, destination_path)
    blockers: set[str] = set()

    if assessment.state is not DatabaseUpgradeReviewState.REVIEW_EVIDENCE_VERIFIED:
        blockers.add("PHASE9M_REVIEW_NOT_VERIFIED")
    if (
        assessment.request_id != request.request_id
        or assessment.request_hash != request.request_hash
        or assessment.config_hash != request.config_hash
    ):
        blockers.add("PHASE9M_EVIDENCE_MISMATCH")
    if not request.maintenance_window_start <= observed_at < request.maintenance_window_end:
        blockers.add("OUTSIDE_MAINTENANCE_WINDOW")

    source_hash: str | None = None
    source_bytes: int | None = None
    quick_check: tuple[str, ...] = ()
    foreign_key_violations: int | None = None
    sidecars = tuple(
        sorted(
            _relative_to_root(Path(f"{source}{suffix}"), root)
            for suffix in ("-journal", "-shm", "-wal")
            if Path(f"{source}{suffix}").exists()
        )
    )
    if sidecars:
        blockers.add("SQLITE_SIDECARS_PRESENT")
    if source.is_symlink():
        blockers.add("SOURCE_SYMLINK")
    if not source.is_file():
        blockers.add("SOURCE_NOT_REGULAR_FILE")
    else:
        source_hash = _file_hash(source)
        source_bytes = source.stat().st_size
        if source_hash != request.source_hash:
            blockers.add("SOURCE_HASH_MISMATCH")
        if not sidecars:
            try:
                connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
                try:
                    connection.execute("PRAGMA query_only=ON")
                    quick_check = tuple(
                        str(row[0]) for row in connection.execute("PRAGMA quick_check")
                    )
                    foreign_key_violations = sum(
                        1 for _ in connection.execute("PRAGMA foreign_key_check")
                    )
                finally:
                    connection.close()
            except sqlite3.DatabaseError:
                blockers.add("SQLITE_INTEGRITY_UNAVAILABLE")
            if quick_check != ("ok",):
                blockers.add("SQLITE_QUICK_CHECK_FAILED")
            if foreign_key_violations not in (0,):
                blockers.add("SQLITE_FOREIGN_KEY_VIOLATIONS")

    if destination_root.is_symlink() or destination.is_symlink():
        blockers.add("DESTINATION_SYMLINK")
    if not destination_root.is_dir():
        blockers.add("DESTINATION_ROOT_UNAVAILABLE")
    if not destination.is_dir():
        blockers.add("DESTINATION_UNAVAILABLE")
    if destination_root != destination and destination_root not in destination.parents:
        blockers.add("DESTINATION_OUTSIDE_APPROVED_ROOT")
    if destination == source.parent or destination in source.parents:
        blockers.add("DESTINATION_OVERLAPS_SOURCE")

    capacity_satisfied = False
    if destination.is_dir():
        capacity_satisfied = shutil.disk_usage(destination).free >= minimum_free_bytes
        if not capacity_satisfied:
            blockers.add("INSUFFICIENT_DESTINATION_SPACE")
    if source_bytes is not None and minimum_free_bytes < source_bytes:
        blockers.add("MINIMUM_FREE_BYTES_BELOW_SOURCE_SIZE")

    target: Path | None = None
    target_already_present = False
    if destination.is_dir() and source_hash is not None:
        target = destination / f"{source.stem}-{source_hash[7:23]}.sqlite"
        if target.exists():
            if target.is_symlink() or not target.is_file():
                blockers.add("TARGET_CONFLICT")
            elif _file_hash(target) == source_hash:
                target_already_present = True
            else:
                blockers.add("TARGET_CONFLICT")

    blocker_codes = tuple(sorted(blockers))
    state = (
        RealDatabaseBackupPreflightState.BLOCKED
        if blocker_codes
        else RealDatabaseBackupPreflightState.BACKUP_ALREADY_PRESENT
        if target_already_present
        else RealDatabaseBackupPreflightState.READY_FOR_BACKUP_REVIEW
    )
    source_text = _relative_to_root(source, root)
    destination_root_text = _relative_to_root(destination_root, root)
    destination_text = _relative_to_root(destination, root)
    target_text = _relative_to_root(target, root) if target is not None else None
    identity = (
        state,
        observed_at,
        request.request_id,
        assessment.assessment_id,
        source_text,
        source_hash,
        source_bytes,
        destination_root_text,
        destination_text,
        target_text,
        minimum_free_bytes,
        capacity_satisfied,
        quick_check,
        foreign_key_violations,
        sidecars,
        quiescence_evidence_hash,
        target_already_present,
        blocker_codes,
        config.config_hash,
    )
    return RealDatabaseBackupPreflight(
        deterministic_id("real_database_backup_preflight", identity),
        state,
        observed_at,
        request.request_id,
        assessment.assessment_id,
        source_text,
        source_hash,
        source_bytes,
        destination_root_text,
        destination_text,
        target_text,
        minimum_free_bytes,
        capacity_satisfied,
        quick_check,
        foreign_key_violations,
        sidecars,
        quiescence_evidence_hash,
        target_already_present,
        blocker_codes,
        config.config_hash,
    )


def _configured_database(config: BackupPreflightConfig, root: Path) -> Path:
    plan_value = config.values["upgrade_plan_config"]
    if not isinstance(plan_value, str):
        raise TypeError("validated Phase 9N plan path must be text")
    plan = load_upgrade_plan_config(root / plan_value)
    readiness_value = plan.values["readiness_config"]
    if not isinstance(readiness_value, str):
        raise TypeError("validated Phase 9K readiness path must be text")
    readiness = load_launch_readiness_config(root / readiness_value)
    local_value = readiness.values["local_status_config"]
    if not isinstance(local_value, str):
        raise TypeError("validated Phase 9J local-status path must be text")
    local = load_local_status_config(root / local_value)
    database_value = local.values["database"]
    if not isinstance(database_value, str) or not _relative(database_value):
        raise BackupPreflightConfigError("Phase 9I database path is invalid")
    raw = root / database_value
    resolved = raw.resolve()
    if root not in resolved.parents:
        raise BackupPreflightConfigError("Phase 9N source escapes project root")
    return raw


def _operator_path(root: Path, value: str) -> Path:
    if not _relative(value):
        raise ValueError("Phase 9N operator paths must be canonical project-relative paths")
    raw = root / value
    resolved = raw.resolve()
    if root not in resolved.parents:
        raise ValueError("Phase 9N operator path escapes project root")
    return raw


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
