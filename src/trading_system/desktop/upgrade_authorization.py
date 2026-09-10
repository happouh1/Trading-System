"""Phase 9M signed review evidence without database-upgrade authority."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from trading_system.desktop.upgrade_plan import LocalSchemaUpgradePlan
from trading_system.desktop.upgrade_rehearsal import UpgradeRehearsalResult
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class DatabaseUpgradeReviewConfigError(ValueError):
    pass


class DatabaseUpgradeReviewState(StrEnum):
    REVIEW_EVIDENCE_VERIFIED = "REVIEW_EVIDENCE_VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class DatabaseUpgradeReviewConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class DatabaseUpgradeReviewCredential:
    credential_id: str
    principal_id: str
    role: str
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        try:
            key = base64.b64decode(self.public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("invalid Phase 9M review credential") from error
        if (
            not all((self.credential_id, self.principal_id, self.role))
            or len(key) != 32
            or any(not _utc(value) for value in (self.valid_from, self.valid_until))
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 9M review credential")


@dataclass(frozen=True, slots=True)
class DatabaseUpgradeReviewRequest:
    request_id: str
    plan_id: str
    plan_hash: str
    rehearsal_id: str
    rehearsal_hash: str
    source_hash: str
    backup_policy_hash: str
    recovery_procedure_hash: str
    quiescence_procedure_hash: str
    requested_at: datetime
    maintenance_window_start: datetime
    maintenance_window_end: datetime
    required_review_roles: tuple[str, ...]
    request_hash: str
    config_hash: str
    authorization_version: str = "9M.1.0"
    real_backup_authorized: bool = False
    real_migration_authorized: bool = False
    restore_promotion_authorized: bool = False
    process_launch_authorized: bool = False
    broker_write_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        hashes = (
            self.plan_hash,
            self.rehearsal_hash,
            self.source_hash,
            self.backup_policy_hash,
            self.recovery_procedure_hash,
            self.quiescence_procedure_hash,
            self.request_hash,
            self.config_hash,
        )
        if (
            not all((self.request_id, self.plan_id, self.rehearsal_id))
            or any(not _sha(value) for value in hashes)
            or any(
                not _utc(value)
                for value in (
                    self.requested_at,
                    self.maintenance_window_start,
                    self.maintenance_window_end,
                )
            )
            or not self.requested_at <= self.maintenance_window_start
            < self.maintenance_window_end
            or not self.required_review_roles
            or self.required_review_roles != tuple(sorted(set(self.required_review_roles)))
            or self.authorization_version != "9M.1.0"
            or any(
                (
                    self.real_backup_authorized,
                    self.real_migration_authorized,
                    self.restore_promotion_authorized,
                    self.process_launch_authorized,
                    self.broker_write_authorized,
                    self.live_trading_authorized,
                )
            )
        ):
            raise ValueError("invalid Phase 9M database-upgrade review request")


@dataclass(frozen=True, slots=True)
class DatabaseUpgradeReviewAttestation:
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
            raise ValueError("invalid Phase 9M review attestation")


@dataclass(frozen=True, slots=True)
class DatabaseUpgradeReviewAssessment:
    assessment_id: str
    request_id: str
    evaluated_at: datetime
    state: DatabaseUpgradeReviewState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    request_hash: str
    config_hash: str
    authorization_version: str = "9M.1.0"
    real_backup_performed: bool = False
    real_migration_performed: bool = False
    restore_promoted: bool = False
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
            or self.authorization_version != "9M.1.0"
            or any(
                (
                    self.real_backup_performed,
                    self.real_migration_performed,
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
            raise ValueError("invalid Phase 9M database-upgrade review assessment")


def load_database_upgrade_review_config(path: str | Path) -> DatabaseUpgradeReviewConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "authorization_version",
        "mode",
        "policy",
        "authority",
    }:
        raise DatabaseUpgradeReviewConfigError("Phase 9M configuration keys are invalid")
    if (
        raw["authorization_version"] != "9M.1.0"
        or raw["mode"] != "OFFLINE_DATABASE_UPGRADE_REVIEW"
    ):
        raise DatabaseUpgradeReviewConfigError("Phase 9M mode is invalid")
    if raw["policy"] != {
        "require_phase9k_upgrade_required": True,
        "require_phase9l_verified_rehearsal": True,
        "require_matching_required_tables": True,
        "require_backup_policy_hash": True,
        "require_recovery_procedure_hash": True,
        "require_quiescence_procedure_hash": True,
        "review_roles_operator_supplied": True,
        "distinct_reviewer_principals": True,
        "signature_algorithm": "Ed25519",
        "bounded_maintenance_window": True,
    }:
        raise DatabaseUpgradeReviewConfigError("Phase 9M policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "default_review_roles_enabled",
        "real_backup_enabled",
        "real_migration_enabled",
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
        raise DatabaseUpgradeReviewConfigError("Phase 9M authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return DatabaseUpgradeReviewConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_database_upgrade_review_request(
    config: DatabaseUpgradeReviewConfig,
    *,
    plan: LocalSchemaUpgradePlan,
    rehearsal: UpgradeRehearsalResult,
    backup_policy_hash: str,
    recovery_procedure_hash: str,
    quiescence_procedure_hash: str,
    requested_at: datetime,
    maintenance_window_start: datetime,
    maintenance_window_end: datetime,
    required_review_roles: tuple[str, ...],
) -> DatabaseUpgradeReviewRequest:
    if plan.plan_status != "REQUIRED" or not plan.backup_required or plan.source_hash is None:
        raise ValueError("Phase 9M requires a Phase 9K backup-required upgrade plan")
    if rehearsal.status != "VERIFIED" or not rehearsal.test_only:
        raise ValueError("Phase 9M requires a verified Phase 9L rehearsal")
    if plan.required_tables != rehearsal.required_tables:
        raise ValueError("Phase 9M plan and rehearsal required tables differ")
    supplied_hashes = (
        backup_policy_hash,
        recovery_procedure_hash,
        quiescence_procedure_hash,
    )
    if any(not _sha(value) for value in supplied_hashes):
        raise ValueError("Phase 9M procedure references must be SHA-256 identities")
    roles = tuple(sorted(required_review_roles))
    plan_hash = canonical_hash(plan)
    rehearsal_hash = canonical_hash(rehearsal)
    content = (
        plan.plan_id,
        plan_hash,
        rehearsal.rehearsal_id,
        rehearsal_hash,
        plan.source_hash,
        *supplied_hashes,
        requested_at,
        maintenance_window_start,
        maintenance_window_end,
        roles,
        config.config_hash,
    )
    return DatabaseUpgradeReviewRequest(
        deterministic_id("database_upgrade_review_request", content),
        plan.plan_id,
        plan_hash,
        rehearsal.rehearsal_id,
        rehearsal_hash,
        plan.source_hash,
        *supplied_hashes,
        requested_at,
        maintenance_window_start,
        maintenance_window_end,
        roles,
        canonical_hash(content),
        config.config_hash,
    )


def build_database_upgrade_review_credential(
    *,
    principal_id: str,
    role: str,
    public_key: bytes,
    valid_from: datetime,
    valid_until: datetime,
) -> DatabaseUpgradeReviewCredential:
    encoded = base64.b64encode(public_key).decode()
    identity = (principal_id, role, encoded, valid_from, valid_until)
    return DatabaseUpgradeReviewCredential(
        deterministic_id("database_upgrade_review_credential", identity),
        principal_id,
        role,
        encoded,
        valid_from,
        valid_until,
    )


def database_upgrade_review_message(
    request: DatabaseUpgradeReviewRequest,
    credential: DatabaseUpgradeReviewCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json(
        (
            request.request_id,
            request.request_hash,
            request.plan_hash,
            request.rehearsal_hash,
            request.source_hash,
            request.backup_policy_hash,
            request.recovery_procedure_hash,
            request.quiescence_procedure_hash,
            request.maintenance_window_start,
            request.maintenance_window_end,
            credential.credential_id,
            credential.principal_id,
            credential.role,
            signed_at,
        )
    ).encode()


def build_database_upgrade_review_attestation(
    request: DatabaseUpgradeReviewRequest,
    credential: DatabaseUpgradeReviewCredential,
    *,
    signed_at: datetime,
    signature: bytes,
) -> DatabaseUpgradeReviewAttestation:
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
    return DatabaseUpgradeReviewAttestation(
        deterministic_id("database_upgrade_review_attestation", identity),
        request.request_id,
        request.request_hash,
        credential.credential_id,
        credential.principal_id,
        credential.role,
        signed_at,
        encoded,
    )


def evaluate_database_upgrade_review(
    request: DatabaseUpgradeReviewRequest,
    *,
    credentials: tuple[DatabaseUpgradeReviewCredential, ...],
    attestations: tuple[DatabaseUpgradeReviewAttestation, ...],
    evaluated_at: datetime,
) -> DatabaseUpgradeReviewAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 9M evaluation time must be UTC")
    credential_by_id = {item.credential_id: item for item in credentials}
    if len(credential_by_id) != len(credentials):
        raise ValueError("Phase 9M credential identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    if not request.maintenance_window_start <= evaluated_at < request.maintenance_window_end:
        reasons.add("OUTSIDE_MAINTENANCE_WINDOW")
    for attestation in sorted(attestations, key=lambda item: (item.role, item.attestation_id)):
        credential = credential_by_id.get(attestation.credential_id)
        if (
            credential is None
            or attestation.request_id != request.request_id
            or attestation.request_hash != request.request_hash
            or attestation.principal_id != credential.principal_id
            or attestation.role != credential.role
            or not credential.valid_from <= attestation.signed_at < credential.valid_until
            or not request.maintenance_window_start
            <= attestation.signed_at
            < request.maintenance_window_end
            or attestation.signed_at > evaluated_at
        ):
            reasons.add("INVALID_ATTESTATION")
            continue
        try:
            Ed25519PublicKey.from_public_bytes(
                base64.b64decode(credential.public_key_base64, validate=True)
            ).verify(
                base64.b64decode(attestation.signature_base64, validate=True),
                database_upgrade_review_message(request, credential, attestation.signed_at),
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
        "OUTSIDE_MAINTENANCE_WINDOW",
        "REVIEWER_SEPARATION_FAILURE",
    }
    if reasons & blocking:
        state = DatabaseUpgradeReviewState.BLOCKED
    elif reasons:
        state = DatabaseUpgradeReviewState.INCOMPLETE
    else:
        state = DatabaseUpgradeReviewState.REVIEW_EVIDENCE_VERIFIED
    reason_codes = tuple(sorted(reasons))
    verified_roles = tuple(sorted(verified))
    identity = (
        request.request_id,
        evaluated_at,
        state,
        verified_roles,
        reason_codes,
        request.request_hash,
    )
    return DatabaseUpgradeReviewAssessment(
        deterministic_id("database_upgrade_review_assessment", identity),
        request.request_id,
        evaluated_at,
        state,
        verified_roles,
        reason_codes,
        request.request_hash,
        request.config_hash,
    )


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
