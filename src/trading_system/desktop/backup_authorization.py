"""Phase 9P signed backup-authorization evidence without execution authority."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from trading_system.desktop.backup_manifest import (
    RealDatabaseBackupManifest,
    RealDatabaseBackupManifestState,
)
from trading_system.desktop.upgrade_authorization import DatabaseUpgradeReviewCredential
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class BackupAuthorizationConfigError(ValueError):
    pass


class BackupAuthorizationEvidenceState(StrEnum):
    BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED = "BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BackupAuthorizationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class BackupAuthorizationRequest:
    request_id: str
    manifest_id: str
    manifest_hash: str
    preflight_id: str
    preflight_hash: str
    source_hash: str
    target_path: str
    execution_component_id: str
    operator_nonce: str
    requested_at: datetime
    valid_from: datetime
    valid_until: datetime
    required_review_roles: tuple[str, ...]
    request_hash: str
    config_hash: str
    authorization_version: str = "9P.1.0"
    execution_authorized: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    broker_write_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.request_id,
                    self.manifest_id,
                    self.preflight_id,
                    self.target_path,
                    self.execution_component_id,
                    self.operator_nonce,
                )
            )
            or any(
                not _sha(value)
                for value in (
                    self.manifest_hash,
                    self.preflight_hash,
                    self.source_hash,
                    self.request_hash,
                    self.config_hash,
                )
            )
            or any(
                not _utc(value)
                for value in (self.requested_at, self.valid_from, self.valid_until)
            )
            or not self.requested_at <= self.valid_from < self.valid_until
            or self.required_review_roles
            != tuple(sorted(set(self.required_review_roles)))
            or not self.required_review_roles
            or self.authorization_version != "9P.1.0"
            or any(
                (
                    self.execution_authorized,
                    self.backup_created,
                    self.database_write_performed,
                    self.broker_write_authorized,
                    self.live_trading_authorized,
                )
            )
        ):
            raise ValueError("invalid Phase 9P backup-authorization request")


@dataclass(frozen=True, slots=True)
class BackupAuthorizationAttestation:
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
            raise ValueError("invalid Phase 9P backup-authorization attestation")


@dataclass(frozen=True, slots=True)
class BackupAuthorizationAssessment:
    assessment_id: str
    request_id: str
    evaluated_at: datetime
    state: BackupAuthorizationEvidenceState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    request_hash: str
    config_hash: str
    authorization_version: str = "9P.1.0"
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
            or self.authorization_version != "9P.1.0"
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
            raise ValueError("invalid Phase 9P backup-authorization assessment")


def load_backup_authorization_config(path: str | Path) -> BackupAuthorizationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "authorization_version",
        "mode",
        "backup_manifest_config",
        "policy",
        "authority",
    }:
        raise BackupAuthorizationConfigError("Phase 9P configuration keys are invalid")
    if (
        raw["authorization_version"] != "9P.1.0"
        or raw["mode"] != "OFFLINE_BACKUP_AUTHORIZATION_EVIDENCE"
        or not _relative(raw["backup_manifest_config"])
    ):
        raise BackupAuthorizationConfigError("Phase 9P mode or manifest path is invalid")
    if raw["policy"] != {
        "require_phase9o_ready_for_authorization_review": True,
        "require_exact_manifest_hash": True,
        "require_exact_source_and_target": True,
        "require_operator_nonce": True,
        "review_roles_operator_supplied": True,
        "distinct_reviewer_principals": True,
        "signature_algorithm": "Ed25519",
        "bounded_authorization_window": True,
    }:
        raise BackupAuthorizationConfigError("Phase 9P policy is invalid")
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
        raise BackupAuthorizationConfigError("Phase 9P authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupAuthorizationConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_backup_authorization_request(
    config: BackupAuthorizationConfig,
    *,
    manifest: RealDatabaseBackupManifest,
    operator_nonce: str,
    requested_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
    required_review_roles: tuple[str, ...],
) -> BackupAuthorizationRequest:
    if manifest.state is not RealDatabaseBackupManifestState.READY_FOR_AUTHORIZATION_REVIEW:
        raise ValueError("Phase 9P requires a review-ready Phase 9O manifest")
    if manifest.source_hash is None or manifest.target_path is None:
        raise ValueError("Phase 9P requires exact source and target identities")
    if not operator_nonce.strip():
        raise ValueError("Phase 9P operator nonce is required")
    roles = tuple(sorted(required_review_roles))
    manifest_hash = canonical_hash(manifest)
    content = (
        manifest.manifest_id,
        manifest_hash,
        manifest.preflight_id,
        manifest.preflight_hash,
        manifest.source_hash,
        manifest.target_path,
        manifest.execution_component_id,
        operator_nonce,
        requested_at,
        valid_from,
        valid_until,
        roles,
        config.config_hash,
    )
    return BackupAuthorizationRequest(
        deterministic_id("backup_authorization_request", content),
        manifest.manifest_id,
        manifest_hash,
        manifest.preflight_id,
        manifest.preflight_hash,
        manifest.source_hash,
        manifest.target_path,
        manifest.execution_component_id,
        operator_nonce,
        requested_at,
        valid_from,
        valid_until,
        roles,
        canonical_hash(content),
        config.config_hash,
    )


def backup_authorization_message(
    request: BackupAuthorizationRequest,
    credential: DatabaseUpgradeReviewCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json(
        (
            request.request_id,
            request.request_hash,
            request.manifest_id,
            request.manifest_hash,
            request.preflight_hash,
            request.source_hash,
            request.target_path,
            request.execution_component_id,
            request.operator_nonce,
            request.valid_from,
            request.valid_until,
            credential.credential_id,
            credential.principal_id,
            credential.role,
            signed_at,
        )
    ).encode()


def build_backup_authorization_attestation(
    request: BackupAuthorizationRequest,
    credential: DatabaseUpgradeReviewCredential,
    *,
    signed_at: datetime,
    signature: bytes,
) -> BackupAuthorizationAttestation:
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
    return BackupAuthorizationAttestation(
        deterministic_id("backup_authorization_attestation", identity),
        request.request_id,
        request.request_hash,
        credential.credential_id,
        credential.principal_id,
        credential.role,
        signed_at,
        encoded,
    )


def evaluate_backup_authorization_evidence(
    request: BackupAuthorizationRequest,
    *,
    credentials: tuple[DatabaseUpgradeReviewCredential, ...],
    attestations: tuple[BackupAuthorizationAttestation, ...],
    evaluated_at: datetime,
) -> BackupAuthorizationAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 9P evaluation time must be UTC")
    credential_by_id = {item.credential_id: item for item in credentials}
    if len(credential_by_id) != len(credentials):
        raise ValueError("Phase 9P credential identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    if not request.valid_from <= evaluated_at < request.valid_until:
        reasons.add("OUTSIDE_AUTHORIZATION_WINDOW")
    for attestation in sorted(attestations, key=lambda item: (item.role, item.attestation_id)):
        credential = credential_by_id.get(attestation.credential_id)
        if (
            credential is None
            or attestation.request_id != request.request_id
            or attestation.request_hash != request.request_hash
            or attestation.principal_id != credential.principal_id
            or attestation.role != credential.role
            or not credential.valid_from <= attestation.signed_at < credential.valid_until
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
                backup_authorization_message(request, credential, attestation.signed_at),
            )
        except (InvalidSignature, ValueError):
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
        "OUTSIDE_AUTHORIZATION_WINDOW",
        "REVIEWER_SEPARATION_FAILURE",
    }
    if reasons & blocking:
        state = BackupAuthorizationEvidenceState.BLOCKED
    elif reasons:
        state = BackupAuthorizationEvidenceState.INCOMPLETE
    else:
        state = BackupAuthorizationEvidenceState.BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED
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
    return BackupAuthorizationAssessment(
        deterministic_id("backup_authorization_assessment", identity),
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
