"""Immutable Phase 5E backup, restore-drill, and retention evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.resilience_config import OperationsResilienceConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class IntegrityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_id: str
    known_at: datetime
    source_path: str
    artifact_path: str
    artifact_hash: str
    artifact_bytes: int
    source_revision: str
    code_version: str
    quick_check: tuple[str, ...]
    foreign_key_violations: int
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "backup known_at")
        _sha(self.artifact_hash, "artifact hash")
        if not all(
            (
                self.backup_id,
                self.source_path,
                self.artifact_path,
                self.source_revision,
                self.code_version,
                self.config_hash,
            )
        ):
            raise ValueError("backup manifest identity is required")
        if self.artifact_bytes <= 0 or self.quick_check != ("ok",):
            raise ValueError("backup artifact must pass SQLite quick_check")
        if self.foreign_key_violations != 0:
            raise ValueError("backup artifact has foreign-key violations")

    @classmethod
    def create(
        cls,
        *,
        known_at: datetime,
        source_path: str,
        artifact_path: str,
        artifact_hash: str,
        artifact_bytes: int,
        source_revision: str,
        config: OperationsResilienceConfig,
    ) -> BackupManifest:
        identity = (
            known_at,
            source_path,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("operations_backup", identity),
            known_at,
            source_path,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            source_revision,
            PACKAGE_VERSION,
            ("ok",),
            0,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class RestoreVerification:
    verification_id: str
    backup_id: str
    known_at: datetime
    restored_path: str
    expected_hash: str
    actual_hash: str
    status: IntegrityStatus
    quick_check: tuple[str, ...]
    foreign_key_violations: int
    promoted: bool
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "restore verification known_at")
        _sha(self.expected_hash, "expected hash")
        _sha(self.actual_hash, "actual hash")
        if not all((self.verification_id, self.backup_id, self.restored_path, self.config_hash)):
            raise ValueError("restore verification identity is required")
        if self.promoted:
            raise ValueError("Phase 5E restore drills cannot promote databases")
        expected = (
            self.expected_hash == self.actual_hash
            and self.quick_check == ("ok",)
            and self.foreign_key_violations == 0
        )
        if (self.status is IntegrityStatus.VERIFIED) is not expected:
            raise ValueError("restore verification status is inconsistent")

    @classmethod
    def create(
        cls,
        *,
        backup_id: str,
        known_at: datetime,
        restored_path: str,
        expected_hash: str,
        actual_hash: str,
        quick_check: tuple[str, ...],
        foreign_key_violations: int,
        config: OperationsResilienceConfig,
    ) -> RestoreVerification:
        status = (
            IntegrityStatus.VERIFIED
            if expected_hash == actual_hash
            and quick_check == ("ok",)
            and foreign_key_violations == 0
            else IntegrityStatus.FAILED
        )
        identity = (
            backup_id,
            known_at,
            restored_path,
            expected_hash,
            actual_hash,
            quick_check,
            foreign_key_violations,
            config.config_hash,
        )
        return cls(
            deterministic_id("operations_restore_verification", identity),
            backup_id,
            known_at,
            restored_path,
            expected_hash,
            actual_hash,
            status,
            quick_check,
            foreign_key_violations,
            False,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class RetentionReport:
    report_id: str
    as_of: datetime
    minimum_retention_days: int
    protected_backup_ids: tuple[str, ...]
    review_eligible_backup_ids: tuple[str, ...]
    deletion_performed: bool
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.as_of, "retention report as_of")
        if self.minimum_retention_days <= 0 or self.deletion_performed:
            raise ValueError("Phase 5E retention is positive and report-only")
        if self.protected_backup_ids != tuple(sorted(set(self.protected_backup_ids))):
            raise ValueError("protected backup IDs must be canonical")
        if self.review_eligible_backup_ids != tuple(sorted(set(self.review_eligible_backup_ids))):
            raise ValueError("eligible backup IDs must be canonical")
        if set(self.protected_backup_ids) & set(self.review_eligible_backup_ids):
            raise ValueError("retention partitions cannot overlap")

    @classmethod
    def create(
        cls,
        *,
        as_of: datetime,
        protected_backup_ids: tuple[str, ...],
        review_eligible_backup_ids: tuple[str, ...],
        config: OperationsResilienceConfig,
    ) -> RetentionReport:
        protected = tuple(sorted(set(protected_backup_ids)))
        eligible = tuple(sorted(set(review_eligible_backup_ids)))
        identity = (as_of, config.minimum_retention_days, protected, eligible, config.config_hash)
        return cls(
            deterministic_id("operations_retention_report", identity),
            as_of,
            config.minimum_retention_days,
            protected,
            eligible,
            False,
            config.config_hash,
        )
