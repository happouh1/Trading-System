"""Phase 9E signed stage-review evidence without stage activation authority."""

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

from trading_system.paper.rollout import RolloutGateAssessment, RolloutGateState
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class StageAuthorizationConfigError(ValueError):
    pass


class StageAuthorizationState(StrEnum):
    SIGNATURES_VERIFIED = "SIGNATURES_VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class StageAuthorizationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class StageReviewCredential:
    credential_id: str
    principal_id: str
    role: str
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        try:
            public_key = base64.b64decode(self.public_key_base64, validate=True)
        except ValueError as error:
            raise ValueError("invalid Phase 9E credential") from error
        if (
            not all((self.credential_id, self.principal_id, self.role))
            or len(public_key) != 32
            or any(
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
                for value in (self.valid_from, self.valid_until)
            )
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 9E credential")


@dataclass(frozen=True, slots=True)
class StageAuthorizationRequest:
    request_id: str
    session_id: str
    rollout_assessment_id: str
    rollout_assessment_hash: str
    plan_id: str
    stage_id: str
    requested_at: datetime
    valid_from: datetime
    valid_until: datetime
    required_review_roles: tuple[str, ...]
    request_hash: str
    config_hash: str
    authorization_version: str = "9E.1.0"
    stage_activation_authorized: bool = False
    deployment_authorized: bool = False
    broker_write_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        timestamps = (self.requested_at, self.valid_from, self.valid_until)
        if (
            not all((self.request_id, self.session_id, self.rollout_assessment_id,
                     self.plan_id, self.stage_id))
            or not self.rollout_assessment_hash.startswith("sha256:")
            or any(
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
                for value in timestamps
            )
            or not self.requested_at <= self.valid_from < self.valid_until
            or not self.required_review_roles
            or self.required_review_roles != tuple(sorted(set(self.required_review_roles)))
            or not self.request_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.authorization_version != "9E.1.0"
            or self.stage_activation_authorized
            or self.deployment_authorized
            or self.broker_write_authorized
            or self.live_trading_authorized
        ):
            raise ValueError("invalid Phase 9E stage-review request")


@dataclass(frozen=True, slots=True)
class StageReviewAttestation:
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
            not all((self.attestation_id, self.request_id, self.credential_id,
                     self.principal_id, self.role, self.signature_base64))
            or not self.request_hash.startswith("sha256:")
            or self.signed_at.tzinfo is None
            or self.signed_at.utcoffset() != UTC.utcoffset(self.signed_at)
        ):
            raise ValueError("invalid Phase 9E stage-review attestation")


@dataclass(frozen=True, slots=True)
class StageAuthorizationAssessment:
    assessment_id: str
    request_id: str
    plan_id: str
    stage_id: str
    evaluated_at: datetime
    state: StageAuthorizationState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    request_hash: str
    config_hash: str
    authorization_version: str = "9E.1.0"
    stage_activated: bool = False
    deployment_performed: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.request_id, self.plan_id, self.stage_id))
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() != UTC.utcoffset(self.evaluated_at)
            or self.verified_roles != tuple(sorted(set(self.verified_roles)))
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not self.request_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.authorization_version != "9E.1.0"
            or self.stage_activated
            or self.deployment_performed
            or self.broker_write_performed
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9E stage-review assessment")


def load_stage_authorization_config(path: str | Path) -> StageAuthorizationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "authorization_version", "mode", "policy", "authority"
    }:
        raise StageAuthorizationConfigError("Phase 9E configuration keys are invalid")
    if raw["authorization_version"] != "9E.1.0" or raw["mode"] != (
        "OFFLINE_SIGNED_STAGE_REVIEW"
    ):
        raise StageAuthorizationConfigError("Phase 9E mode is invalid")
    if raw["policy"] != {
        "require_phase9d_human_review_ready": True,
        "review_roles_operator_supplied": True,
        "distinct_reviewer_principals": True,
        "signature_algorithm": "Ed25519",
        "exact_stage_scope": True,
        "bounded_validity_window": True,
        "assessments_per_request": 1,
    }:
        raise StageAuthorizationConfigError("Phase 9E policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or any(value is not False for value in authority.values()):
        raise StageAuthorizationConfigError("Phase 9E authority must remain disabled")
    if set(authority) != {
        "default_review_roles_enabled", "stage_activation_enabled",
        "automatic_advancement_enabled", "deployment_enabled", "network_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }:
        raise StageAuthorizationConfigError("Phase 9E authority keys are invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return StageAuthorizationConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_stage_review_credential(
    *, principal_id: str, role: str, public_key: bytes,
    valid_from: datetime, valid_until: datetime,
) -> StageReviewCredential:
    encoded_key = base64.b64encode(public_key).decode()
    core = (principal_id, role, encoded_key, valid_from, valid_until)
    return StageReviewCredential(
        deterministic_id("stage_review_credential", core), principal_id, role,
        encoded_key, valid_from, valid_until,
    )


def build_stage_authorization_request(
    config: StageAuthorizationConfig,
    *,
    rollout_assessment: RolloutGateAssessment,
    session_id: str,
    requested_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
    required_review_roles: tuple[str, ...],
) -> StageAuthorizationRequest:
    if rollout_assessment.state is not RolloutGateState.READY_FOR_HUMAN_REVIEW:
        raise ValueError("Phase 9E requires Phase 9D human-review-ready evidence")
    roles = tuple(sorted(required_review_roles))
    content = (
        session_id, rollout_assessment.assessment_id, canonical_hash(rollout_assessment),
        rollout_assessment.plan_id, rollout_assessment.stage_id, requested_at,
        valid_from, valid_until, roles, config.config_hash,
    )
    return StageAuthorizationRequest(
        deterministic_id("stage_authorization_request", content), session_id,
        rollout_assessment.assessment_id, canonical_hash(rollout_assessment),
        rollout_assessment.plan_id, rollout_assessment.stage_id, requested_at,
        valid_from, valid_until, roles, canonical_hash(content), config.config_hash,
    )


def stage_review_message(
    request: StageAuthorizationRequest,
    credential: StageReviewCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json((
        request.request_id, request.request_hash, request.plan_id, request.stage_id,
        request.valid_from, request.valid_until, credential.credential_id,
        credential.principal_id, credential.role, signed_at,
    )).encode()


def build_stage_review_attestation(
    request: StageAuthorizationRequest,
    credential: StageReviewCredential,
    *,
    signed_at: datetime,
    signature: bytes,
) -> StageReviewAttestation:
    encoded_signature = base64.b64encode(signature).decode()
    core = (
        request.request_id, request.request_hash, credential.credential_id,
        credential.principal_id, credential.role, signed_at, encoded_signature,
    )
    return StageReviewAttestation(
        deterministic_id("stage_review_attestation", core), request.request_id,
        request.request_hash, credential.credential_id, credential.principal_id,
        credential.role, signed_at, encoded_signature,
    )


def evaluate_stage_authorization(
    request: StageAuthorizationRequest,
    *,
    credentials: tuple[StageReviewCredential, ...],
    attestations: tuple[StageReviewAttestation, ...],
    evaluated_at: datetime,
) -> StageAuthorizationAssessment:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise ValueError("Phase 9E evaluation time must be UTC")
    credential_by_id = {item.credential_id: item for item in credentials}
    if len(credential_by_id) != len(credentials):
        raise ValueError("Phase 9E credential identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    if not request.valid_from <= evaluated_at < request.valid_until:
        reasons.add("REQUEST_OUTSIDE_VALIDITY_WINDOW")
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
            Ed25519PublicKey.from_public_bytes(base64.b64decode(
                credential.public_key_base64, validate=True
            )).verify(
                base64.b64decode(attestation.signature_base64, validate=True),
                stage_review_message(request, credential, attestation.signed_at),
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
    if reasons & {
        "INVALID_ATTESTATION", "REVIEWER_SEPARATION_FAILURE",
        "REQUEST_OUTSIDE_VALIDITY_WINDOW",
    }:
        state = StageAuthorizationState.BLOCKED
    elif reasons:
        state = StageAuthorizationState.INCOMPLETE
    else:
        state = StageAuthorizationState.SIGNATURES_VERIFIED
    reason_codes = tuple(sorted(reasons))
    identity = (
        request.request_id, evaluated_at, state, tuple(sorted(verified)), reason_codes,
        request.request_hash,
    )
    return StageAuthorizationAssessment(
        deterministic_id("stage_authorization_assessment", identity), request.request_id,
        request.plan_id, request.stage_id, evaluated_at, state, tuple(sorted(verified)),
        reason_codes, request.request_hash, request.config_hash,
    )
