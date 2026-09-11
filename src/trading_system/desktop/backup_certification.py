"""Phase 9S signed production-backup readiness certification evidence."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from trading_system.desktop.backup_readiness import (
    ProductionBackupReadinessAssessment,
    ProductionBackupReadinessState,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class BackupReadinessCertificationConfigError(ValueError):
    pass


class ProductionBackupReadinessCertificationState(StrEnum):
    READINESS_CERTIFICATION_EVIDENCE_VERIFIED = (
        "READINESS_CERTIFICATION_EVIDENCE_VERIFIED"
    )
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BackupReadinessCertificationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ProductionBackupReadinessCredential:
    credential_id: str
    principal_id: str
    role: str
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        try:
            key = base64.b64decode(self.public_key_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("invalid Phase 9S reviewer credential") from error
        if (
            not all((self.credential_id, self.principal_id, self.role))
            or len(key) != 32
            or any(not _utc(value) for value in (self.valid_from, self.valid_until))
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 9S reviewer credential")


@dataclass(frozen=True, slots=True)
class ProductionBackupReadinessCertificationRequest:
    request_id: str
    readiness_assessment_id: str
    readiness_assessment_hash: str
    authorization_request_id: str
    authorization_request_hash: str
    rehearsal_id: str
    control_evidence_hashes: tuple[tuple[str, str], ...]
    operator_nonce: str
    requested_at: datetime
    valid_from: datetime
    valid_until: datetime
    required_review_roles: tuple[str, ...]
    request_hash: str
    config_hash: str
    certification_version: str = "9S.1.0"
    execution_authorized: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    process_launch_authorized: bool = False
    broker_write_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.request_id,
                    self.readiness_assessment_id,
                    self.authorization_request_id,
                    self.rehearsal_id,
                    self.operator_nonce,
                )
            )
            or any(
                not _sha(value)
                for value in (
                    self.readiness_assessment_hash,
                    self.authorization_request_hash,
                    self.request_hash,
                    self.config_hash,
                )
            )
            or self.control_evidence_hashes
            != tuple(sorted(set(self.control_evidence_hashes)))
            or not self.control_evidence_hashes
            or any(
                not control_id or not _sha(value)
                for control_id, value in self.control_evidence_hashes
            )
            or any(
                not _utc(value)
                for value in (self.requested_at, self.valid_from, self.valid_until)
            )
            or not self.requested_at <= self.valid_from < self.valid_until
            or not self.required_review_roles
            or self.required_review_roles != tuple(sorted(set(self.required_review_roles)))
            or self.certification_version != "9S.1.0"
            or any(
                (
                    self.execution_authorized,
                    self.backup_created,
                    self.database_write_performed,
                    self.process_launch_authorized,
                    self.broker_write_authorized,
                    self.live_trading_authorized,
                )
            )
        ):
            raise ValueError("invalid Phase 9S readiness-certification request")


@dataclass(frozen=True, slots=True)
class ProductionBackupReadinessAttestation:
    attestation_id: str
    request_id: str
    request_hash: str
    credential_id: str
    principal_id: str
    role: str
    signed_at: datetime
    signature_base64: str

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.attestation_id,
                    self.request_id,
                    self.credential_id,
                    self.principal_id,
                    self.role,
                    self.signature_base64,
                )
            )
            or not _sha(self.request_hash)
            or not _utc(self.signed_at)
        ):
            raise ValueError("invalid Phase 9S readiness attestation")


@dataclass(frozen=True, slots=True)
class ProductionBackupReadinessCertificationAssessment:
    assessment_id: str
    request_id: str
    evaluated_at: datetime
    state: ProductionBackupReadinessCertificationState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    request_hash: str
    config_hash: str
    certification_version: str = "9S.1.0"
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
        if (
            not all((self.assessment_id, self.request_id))
            or not _utc(self.evaluated_at)
            or self.verified_roles != tuple(sorted(set(self.verified_roles)))
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not _sha(self.request_hash)
            or not _sha(self.config_hash)
            or self.certification_version != "9S.1.0"
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
            raise ValueError("invalid Phase 9S readiness-certification assessment")


def load_backup_readiness_certification_config(
    path: str | Path,
) -> BackupReadinessCertificationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "certification_version",
        "mode",
        "readiness_config",
        "policy",
        "authority",
    }:
        raise BackupReadinessCertificationConfigError("Phase 9S configuration keys are invalid")
    if (
        raw["certification_version"] != "9S.1.0"
        or raw["mode"] != "OFFLINE_PRODUCTION_BACKUP_READINESS_CERTIFICATION"
        or not _relative(raw["readiness_config"])
    ):
        raise BackupReadinessCertificationConfigError("Phase 9S mode or readiness path is invalid")
    if raw["policy"] != {
        "require_phase9r_ready_for_review": True,
        "require_exact_assessment_hash": True,
        "require_exact_control_evidence_hashes": True,
        "require_operator_nonce": True,
        "review_roles_operator_supplied": True,
        "distinct_reviewer_principals": True,
        "signature_algorithm": "Ed25519",
        "bounded_certification_window": True,
    }:
        raise BackupReadinessCertificationConfigError("Phase 9S policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "execution_authority_enabled",
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
        raise BackupReadinessCertificationConfigError("Phase 9S authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupReadinessCertificationConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_production_backup_readiness_certification_request(
    config: BackupReadinessCertificationConfig,
    *,
    readiness: ProductionBackupReadinessAssessment,
    operator_nonce: str,
    requested_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
    required_review_roles: tuple[str, ...],
) -> ProductionBackupReadinessCertificationRequest:
    if (
        readiness.state
        is not ProductionBackupReadinessState.READY_FOR_EXECUTION_AUTHORIZATION_REVIEW
    ):
        raise ValueError("Phase 9S requires a review-ready Phase 9R assessment")
    if not operator_nonce.strip():
        raise ValueError("Phase 9S operator nonce is required")
    roles = tuple(sorted(required_review_roles))
    readiness_hash = canonical_hash(readiness)
    content = (
        readiness.assessment_id,
        readiness_hash,
        readiness.authorization_request_id,
        readiness.authorization_request_hash,
        readiness.rehearsal_id,
        readiness.evidence_hashes,
        operator_nonce,
        requested_at,
        valid_from,
        valid_until,
        roles,
        config.config_hash,
    )
    return ProductionBackupReadinessCertificationRequest(
        deterministic_id("production_backup_readiness_certification_request", content),
        readiness.assessment_id,
        readiness_hash,
        readiness.authorization_request_id,
        readiness.authorization_request_hash,
        readiness.rehearsal_id,
        readiness.evidence_hashes,
        operator_nonce,
        requested_at,
        valid_from,
        valid_until,
        roles,
        canonical_hash(content),
        config.config_hash,
    )


def build_production_backup_readiness_credential(
    *,
    principal_id: str,
    role: str,
    public_key: bytes,
    valid_from: datetime,
    valid_until: datetime,
) -> ProductionBackupReadinessCredential:
    encoded = base64.b64encode(public_key).decode()
    content = (principal_id, role, encoded, valid_from, valid_until)
    return ProductionBackupReadinessCredential(
        deterministic_id("production_backup_readiness_credential", content),
        principal_id,
        role,
        encoded,
        valid_from,
        valid_until,
    )


def production_backup_readiness_certification_message(
    request: ProductionBackupReadinessCertificationRequest,
    credential: ProductionBackupReadinessCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json(
        (
            request.request_id,
            request.request_hash,
            request.readiness_assessment_id,
            request.readiness_assessment_hash,
            request.authorization_request_id,
            request.authorization_request_hash,
            request.rehearsal_id,
            request.control_evidence_hashes,
            request.operator_nonce,
            request.valid_from,
            request.valid_until,
            credential.credential_id,
            credential.principal_id,
            credential.role,
            signed_at,
        )
    ).encode()


def build_production_backup_readiness_attestation(
    request: ProductionBackupReadinessCertificationRequest,
    credential: ProductionBackupReadinessCredential,
    *,
    signed_at: datetime,
    signature: bytes,
) -> ProductionBackupReadinessAttestation:
    encoded = base64.b64encode(signature).decode()
    identity = (
        request.request_id,
        request.request_hash,
        credential.credential_id,
        credential.principal_id,
        credential.role,
        signed_at,
        encoded,
    )
    return ProductionBackupReadinessAttestation(
        deterministic_id("production_backup_readiness_attestation", identity),
        request.request_id,
        request.request_hash,
        credential.credential_id,
        credential.principal_id,
        credential.role,
        signed_at,
        encoded,
    )


def evaluate_production_backup_readiness_certification(
    request: ProductionBackupReadinessCertificationRequest,
    *,
    credentials: tuple[ProductionBackupReadinessCredential, ...],
    attestations: tuple[ProductionBackupReadinessAttestation, ...],
    evaluated_at: datetime,
) -> ProductionBackupReadinessCertificationAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 9S evaluation time must be UTC")
    credential_by_id = {item.credential_id: item for item in credentials}
    if len(credential_by_id) != len(credentials):
        raise ValueError("Phase 9S credential identities must be unique")
    if len({item.attestation_id for item in attestations}) != len(attestations):
        raise ValueError("Phase 9S attestation identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    if not request.valid_from <= evaluated_at < request.valid_until:
        reasons.add("OUTSIDE_CERTIFICATION_WINDOW")
    for attestation in sorted(attestations, key=lambda item: (item.role, item.attestation_id)):
        credential = credential_by_id.get(attestation.credential_id)
        if (
            credential is None
            or attestation.request_id != request.request_id
            or attestation.request_hash != request.request_hash
            or attestation.principal_id != credential.principal_id
            or attestation.role != credential.role
            or attestation.role not in request.required_review_roles
            or not credential.valid_from <= attestation.signed_at < credential.valid_until
            or not credential.valid_from <= evaluated_at < credential.valid_until
            or not request.valid_from <= attestation.signed_at < request.valid_until
            or attestation.signed_at > evaluated_at
        ):
            reasons.add("INVALID_ATTESTATION")
            continue
        try:
            Ed25519PublicKey.from_public_bytes(
                base64.b64decode(credential.public_key_base64, validate=True)
            ).verify(
                base64.b64decode(attestation.signature_base64, validate=True),
                production_backup_readiness_certification_message(
                    request, credential, attestation.signed_at
                ),
            )
        except (InvalidSignature, ValueError, binascii.Error):
            reasons.add("INVALID_ATTESTATION")
            continue
        if attestation.role in verified or attestation.principal_id in verified.values():
            reasons.add("REVIEWER_SEPARATION_FAILURE")
            continue
        verified[attestation.role] = attestation.principal_id
    if set(request.required_review_roles) - set(verified):
        reasons.add("REQUIRED_REVIEW_ATTESTATION_MISSING")
    blocking = {
        "INVALID_ATTESTATION",
        "OUTSIDE_CERTIFICATION_WINDOW",
        "REVIEWER_SEPARATION_FAILURE",
    }
    if reasons & blocking:
        state = ProductionBackupReadinessCertificationState.BLOCKED
    elif reasons:
        state = ProductionBackupReadinessCertificationState.INCOMPLETE
    else:
        state = (
            ProductionBackupReadinessCertificationState.READINESS_CERTIFICATION_EVIDENCE_VERIFIED
        )
    roles = tuple(sorted(verified))
    reason_codes = tuple(sorted(reasons))
    identity = (
        request.request_id,
        evaluated_at,
        state,
        roles,
        reason_codes,
        request.request_hash,
    )
    return ProductionBackupReadinessCertificationAssessment(
        deterministic_id("production_backup_readiness_certification_assessment", identity),
        request.request_id,
        evaluated_at,
        state,
        roles,
        reason_codes,
        request.request_hash,
        request.config_hash,
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
