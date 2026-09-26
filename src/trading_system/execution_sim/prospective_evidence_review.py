"""Offline signed review evidence for Phase 11J corroborated inputs."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from trading_system.execution_sim.prospective_evidence import CorroboratedProspectiveInputs
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

VERSION = "11K.1.0"


class EvidenceReviewState(StrEnum):
    SIGNATURES_VERIFIED = "SIGNATURES_VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class EvidenceReviewConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class EvidenceReviewCredential:
    credential_id: str
    principal_id: str
    role: str
    public_key_base64: str
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        try:
            key = base64.b64decode(self.public_key_base64, validate=True)
        except ValueError as exc:
            raise ValueError("invalid Phase 11K credential") from exc
        if (
            not all((self.credential_id, self.principal_id, self.role))
            or len(key) != 32
            or not all(_utc(value) for value in (self.valid_from, self.valid_until))
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 11K credential")


@dataclass(frozen=True, slots=True)
class EvidenceReviewRequest:
    request_id: str
    decision_id: str
    receipt_id: str
    receipt_hash: str
    evidence_ids: tuple[str, ...]
    source_bytes_hashes: tuple[str, ...]
    requested_at: datetime
    valid_from: datetime
    valid_until: datetime
    required_review_roles: tuple[str, ...]
    request_hash: str
    config_hash: str
    review_version: str = VERSION
    source_authenticity_asserted: bool = field(default=False, init=False)
    control_override_authorized: bool = field(default=False, init=False)
    broker_write_authorized: bool = field(default=False, init=False)
    qualifying_trade_authorized: bool = field(default=False, init=False)
    cohort_activation_authorized: bool = field(default=False, init=False)
    live_trading_authorized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        times = (self.requested_at, self.valid_from, self.valid_until)
        if (
            not all((self.request_id, self.decision_id, self.receipt_id))
            or not _sha(self.receipt_hash) or not _sha(self.request_hash)
            or not _sha(self.config_hash)
            or not all(_sha(item) for item in self.source_bytes_hashes)
            or not self.evidence_ids or len(self.evidence_ids) != len(self.source_bytes_hashes)
            or self.evidence_ids != tuple(sorted(set(self.evidence_ids)))
            or not all(_utc(value) for value in times)
            or not self.requested_at <= self.valid_from < self.valid_until
            or not self.required_review_roles
            or self.required_review_roles != tuple(sorted(set(self.required_review_roles)))
            or self.review_version != VERSION
        ):
            raise ValueError("invalid Phase 11K review request")


@dataclass(frozen=True, slots=True)
class EvidenceReviewAttestation:
    attestation_id: str
    request_id: str
    request_hash: str
    credential_id: str
    principal_id: str
    role: str
    signed_at: datetime
    signature_base64: str

    def __post_init__(self) -> None:
        try:
            signature = base64.b64decode(self.signature_base64, validate=True)
        except ValueError as exc:
            raise ValueError("invalid Phase 11K attestation") from exc
        if (
            not all((self.attestation_id, self.request_id, self.credential_id,
                     self.principal_id, self.role))
            or not _sha(self.request_hash) or not _utc(self.signed_at)
            or len(signature) != 64
        ):
            raise ValueError("invalid Phase 11K attestation")


@dataclass(frozen=True, slots=True)
class EvidenceReviewAssessment:
    assessment_id: str
    request_id: str
    decision_id: str
    receipt_id: str
    receipt_hash: str
    evaluated_at: datetime
    state: EvidenceReviewState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    request_hash: str
    config_hash: str
    review_version: str = VERSION
    source_authenticity_verified: bool = field(default=False, init=False)
    control_override_performed: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    qualifying_trade: bool = field(default=False, init=False)
    cohort_activated: bool = field(default=False, init=False)
    live_trading_enabled: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.request_id, self.decision_id, self.receipt_id))
            or not _sha(self.receipt_hash) or not _sha(self.request_hash)
            or not _sha(self.config_hash) or not _utc(self.evaluated_at)
            or self.verified_roles != tuple(sorted(set(self.verified_roles)))
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or self.review_version != VERSION
        ):
            raise ValueError("invalid Phase 11K review assessment")


def load_evidence_review_config(path: str | Path) -> EvidenceReviewConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"review_version", "mode", "policy", "authority"}:
        raise ValueError("Phase 11K configuration keys are invalid")
    if raw["review_version"] != VERSION or raw["mode"] != (
        "OFFLINE_SIGNED_PROSPECTIVE_EVIDENCE_REVIEW"
    ):
        raise ValueError("Phase 11K mode is invalid")
    if raw["policy"] != {
        "review_roles_operator_supplied": True,
        "distinct_reviewer_principals": True,
        "signature_algorithm": "Ed25519",
        "exact_receipt_scope": True,
        "bounded_validity_window": True,
        "assessments_per_request": 1,
    }:
        raise ValueError("Phase 11K policy is invalid")
    authority = raw["authority"]
    expected = {
        "source_authenticity_assertion_enabled", "control_override_enabled", "network_enabled",
        "broker_writes_enabled", "qualifying_trade_enabled", "cohort_activation_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict) or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise ValueError("Phase 11K authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return EvidenceReviewConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_evidence_review_credential(
    *, principal_id: str, role: str, public_key: bytes,
    valid_from: datetime, valid_until: datetime,
) -> EvidenceReviewCredential:
    encoded = base64.b64encode(public_key).decode()
    identity = (principal_id, role, encoded, valid_from, valid_until)
    return EvidenceReviewCredential(
        deterministic_id("prospective_evidence_review_credential", identity),
        principal_id, role, encoded, valid_from, valid_until,
    )


def build_evidence_review_request(
    config: EvidenceReviewConfig, evidence: CorroboratedProspectiveInputs, *,
    requested_at: datetime, valid_from: datetime, valid_until: datetime,
    required_review_roles: tuple[str, ...],
) -> EvidenceReviewRequest:
    roles = tuple(sorted(required_review_roles))
    receipt_hash = canonical_hash(evidence)
    content = (
        evidence.decision_id, evidence.receipt_id, receipt_hash, evidence.evidence_ids,
        evidence.source_bytes_hashes, requested_at, valid_from, valid_until, roles,
        config.config_hash,
    )
    return EvidenceReviewRequest(
        deterministic_id("prospective_evidence_review_request", content), evidence.decision_id,
        evidence.receipt_id, receipt_hash, evidence.evidence_ids, evidence.source_bytes_hashes,
        requested_at, valid_from, valid_until, roles, canonical_hash(content), config.config_hash,
    )


def evidence_review_message(
    request: EvidenceReviewRequest, credential: EvidenceReviewCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json((
        request.request_id, request.request_hash, request.decision_id, request.receipt_id,
        request.receipt_hash, request.evidence_ids, request.source_bytes_hashes,
        request.valid_from, request.valid_until, credential.credential_id,
        credential.principal_id, credential.role, signed_at,
    )).encode()


def build_evidence_review_attestation(
    request: EvidenceReviewRequest, credential: EvidenceReviewCredential, *,
    signed_at: datetime, signature: bytes,
) -> EvidenceReviewAttestation:
    encoded = base64.b64encode(signature).decode()
    identity = (
        request.request_id, request.request_hash, credential.credential_id,
        credential.principal_id, credential.role, signed_at, encoded,
    )
    return EvidenceReviewAttestation(
        deterministic_id("prospective_evidence_review_attestation", identity),
        request.request_id, request.request_hash, credential.credential_id,
        credential.principal_id, credential.role, signed_at, encoded,
    )


def evaluate_evidence_review(
    request: EvidenceReviewRequest, *, credentials: tuple[EvidenceReviewCredential, ...],
    attestations: tuple[EvidenceReviewAttestation, ...], evaluated_at: datetime,
) -> EvidenceReviewAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 11K evaluation time must be UTC")
    credential_by_id = {item.credential_id: item for item in credentials}
    if len(credential_by_id) != len(credentials):
        raise ValueError("Phase 11K credential identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    if not request.valid_from <= evaluated_at < request.valid_until:
        reasons.add("REQUEST_OUTSIDE_VALIDITY_WINDOW")
    for attestation in sorted(attestations, key=lambda item: (item.role, item.attestation_id)):
        credential = credential_by_id.get(attestation.credential_id)
        if (
            credential is None or attestation.request_id != request.request_id
            or attestation.request_hash != request.request_hash
            or attestation.principal_id != credential.principal_id
            or attestation.role != credential.role
            or attestation.role not in request.required_review_roles
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
                evidence_review_message(request, credential, attestation.signed_at),
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
    hard = {"INVALID_ATTESTATION", "REVIEWER_SEPARATION_FAILURE", "REQUEST_OUTSIDE_VALIDITY_WINDOW"}
    state = (
        EvidenceReviewState.BLOCKED if reasons & hard
        else EvidenceReviewState.INCOMPLETE if reasons
        else EvidenceReviewState.SIGNATURES_VERIFIED
    )
    roles, reason_codes = tuple(sorted(verified)), tuple(sorted(reasons))
    identity = (request.request_id, evaluated_at, state, roles, reason_codes, request.request_hash)
    return EvidenceReviewAssessment(
        deterministic_id("prospective_evidence_review_assessment", identity), request.request_id,
        request.decision_id, request.receipt_id, request.receipt_hash, evaluated_at, state, roles,
        reason_codes, request.request_hash, request.config_hash,
    )


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _sha(value: str) -> bool:
    return (
        len(value) == 71 and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
