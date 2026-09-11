"""Phase 9R offline production-backup readiness evidence matrix."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.backup_authorization import (
    BackupAuthorizationAssessment,
    BackupAuthorizationEvidenceState,
    BackupAuthorizationRequest,
)
from trading_system.desktop.backup_rehearsal import AuthorizedBackupRehearsalResult
from trading_system.serialization import canonical_hash, deterministic_id


class BackupReadinessConfigError(ValueError):
    pass


class ProductionBackupReadinessState(StrEnum):
    READY_FOR_EXECUTION_AUTHORIZATION_REVIEW = "READY_FOR_EXECUTION_AUTHORIZATION_REVIEW"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"


class ProductionBackupControlState(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class BackupReadinessConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ProductionBackupControlEvidence:
    control_id: str
    state: ProductionBackupControlState
    evidence_hash: str
    verified_by: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if (
            not all((self.control_id, self.verified_by))
            or not _sha(self.evidence_hash)
            or not _utc(self.valid_from)
            or not _utc(self.valid_until)
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 9R production-backup control evidence")


@dataclass(frozen=True, slots=True)
class ProductionBackupReadinessAssessment:
    assessment_id: str
    state: ProductionBackupReadinessState
    evaluated_at: datetime
    authorization_request_id: str
    authorization_request_hash: str
    authorization_assessment_id: str
    rehearsal_id: str
    verified_controls: tuple[str, ...]
    missing_controls: tuple[str, ...]
    unverified_controls: tuple[str, ...]
    blocker_codes: tuple[str, ...]
    evidence_hashes: tuple[tuple[str, str], ...]
    config_hash: str
    readiness_version: str = "9R.1.0"
    execution_authorized: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        collections = (
            self.verified_controls,
            self.missing_controls,
            self.unverified_controls,
            self.blocker_codes,
        )
        expected = (
            ProductionBackupReadinessState.BLOCKED
            if self.blocker_codes
            else ProductionBackupReadinessState.NOT_READY
            if self.missing_controls or self.unverified_controls
            else ProductionBackupReadinessState.READY_FOR_EXECUTION_AUTHORIZATION_REVIEW
        )
        if (
            not all(
                (
                    self.assessment_id,
                    self.authorization_request_id,
                    self.authorization_assessment_id,
                    self.rehearsal_id,
                )
            )
            or not _utc(self.evaluated_at)
            or not _sha(self.authorization_request_hash)
            or not _sha(self.config_hash)
            or any(value != tuple(sorted(set(value))) for value in collections)
            or self.evidence_hashes != tuple(sorted(set(self.evidence_hashes)))
            or self.state is not expected
            or self.readiness_version != "9R.1.0"
            or any(
                (
                    self.execution_authorized,
                    self.backup_created,
                    self.database_write_performed,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9R production-backup readiness assessment")


def load_backup_readiness_config(path: str | Path) -> BackupReadinessConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "readiness_version",
        "mode",
        "rehearsal_config",
        "required_controls",
        "policy",
        "authority",
    }:
        raise BackupReadinessConfigError("Phase 9R configuration keys are invalid")
    if (
        raw["readiness_version"] != "9R.1.0"
        or raw["mode"] != "OFFLINE_PRODUCTION_BACKUP_READINESS_MATRIX"
        or not _relative(raw["rehearsal_config"])
    ):
        raise BackupReadinessConfigError("Phase 9R mode or rehearsal path is invalid")
    expected_controls = [
        "ATOMIC_WRITE_DURABILITY_VERIFIED",
        "CRASH_RECOVERY_APPROVED",
        "ENCRYPTED_DESTINATION_APPROVED",
        "EXECUTOR_AUTHENTICATION_READY",
        "IDENTITY_REVOCATION_READY",
        "IMMUTABLE_AUDIT_STORE_READY",
        "KEY_CUSTODY_APPROVED",
        "REHEARSAL_INDEPENDENTLY_CERTIFIED",
        "RETENTION_POLICY_APPROVED",
        "TRUSTED_CLOCK_READY",
        "TRUSTED_NONCE_SERVICE_READY",
    ]
    if raw["required_controls"] != expected_controls:
        raise BackupReadinessConfigError("Phase 9R required controls are invalid")
    if raw["policy"] != {
        "require_phase9p_verified_evidence": True,
        "require_phase9q_verified_rehearsal": True,
        "require_exact_request_binding": True,
        "control_evidence_operator_supplied": True,
        "control_evidence_time_bounded": True,
        "missing_controls_not_ready": True,
        "invalid_or_expired_controls_block": True,
    }:
        raise BackupReadinessConfigError("Phase 9R policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "execution_authorization_enabled",
        "backup_creation_enabled",
        "directory_creation_enabled",
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
        raise BackupReadinessConfigError("Phase 9R authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value))
        if isinstance(value, dict)
        else tuple(value)
        if isinstance(value, list)
        else value
        for key, value in raw.items()
    }
    return BackupReadinessConfig(MappingProxyType(frozen), canonical_hash(raw))


def assess_production_backup_readiness(
    config: BackupReadinessConfig,
    *,
    request: BackupAuthorizationRequest,
    authorization_assessment: BackupAuthorizationAssessment,
    rehearsal: AuthorizedBackupRehearsalResult,
    control_evidence: tuple[ProductionBackupControlEvidence, ...],
    evaluated_at: datetime,
) -> ProductionBackupReadinessAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 9R evaluation time must be UTC")
    required_value = config.values["required_controls"]
    if not isinstance(required_value, tuple):
        raise TypeError("validated Phase 9R controls must be a tuple")
    required = tuple(str(value) for value in required_value)
    evidence_by_id = {item.control_id: item for item in control_evidence}
    if len(evidence_by_id) != len(control_evidence):
        raise ValueError("Phase 9R control identities must be unique")
    unknown = tuple(sorted(set(evidence_by_id) - set(required)))
    if unknown:
        raise ValueError("Phase 9R received unknown control evidence")
    blockers: set[str] = set()
    if (
        authorization_assessment.state
        is not BackupAuthorizationEvidenceState.BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED
    ):
        blockers.add("PHASE9P_EVIDENCE_NOT_VERIFIED")
    if (
        authorization_assessment.request_id != request.request_id
        or authorization_assessment.request_hash != request.request_hash
        or authorization_assessment.config_hash != request.config_hash
    ):
        blockers.add("PHASE9P_REQUEST_MISMATCH")
    if rehearsal.status != "VERIFIED" or not rehearsal.test_only:
        blockers.add("PHASE9Q_REHEARSAL_NOT_VERIFIED")
    if rehearsal.request_id != request.request_id:
        blockers.add("PHASE9Q_REQUEST_MISMATCH")
    verified: list[str] = []
    unverified: list[str] = []
    evidence_hashes: list[tuple[str, str]] = []
    for control_id in required:
        evidence = evidence_by_id.get(control_id)
        if evidence is None:
            continue
        evidence_hashes.append((control_id, evidence.evidence_hash))
        if not evidence.valid_from <= evaluated_at < evidence.valid_until:
            blockers.add(f"EXPIRED_CONTROL:{control_id}")
        elif evidence.state is ProductionBackupControlState.VERIFIED:
            verified.append(control_id)
        else:
            unverified.append(control_id)
    missing = tuple(sorted(set(required) - set(evidence_by_id)))
    verified_controls = tuple(sorted(verified))
    unverified_controls = tuple(sorted(unverified))
    blocker_codes = tuple(sorted(blockers))
    if blocker_codes:
        state = ProductionBackupReadinessState.BLOCKED
    elif missing or unverified_controls:
        state = ProductionBackupReadinessState.NOT_READY
    else:
        state = ProductionBackupReadinessState.READY_FOR_EXECUTION_AUTHORIZATION_REVIEW
    hashes = tuple(sorted(evidence_hashes))
    identity = (
        state,
        evaluated_at,
        request.request_id,
        request.request_hash,
        authorization_assessment.assessment_id,
        rehearsal.rehearsal_id,
        verified_controls,
        missing,
        unverified_controls,
        blocker_codes,
        hashes,
        config.config_hash,
    )
    return ProductionBackupReadinessAssessment(
        deterministic_id("production_backup_readiness_assessment", identity),
        state,
        evaluated_at,
        request.request_id,
        request.request_hash,
        authorization_assessment.assessment_id,
        rehearsal.rehearsal_id,
        verified_controls,
        missing,
        unverified_controls,
        blocker_codes,
        hashes,
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
