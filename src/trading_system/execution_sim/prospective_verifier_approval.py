"""Offline signed approval of an exact Phase 11M verifier-receipt bundle."""

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

from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

VERSION = "11N.1.0"


class VerifierApprovalState(StrEnum):
    APPROVED = "APPROVED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class VerifierApprovalConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class VerifierApprovalCredential:
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
            raise ValueError("invalid Phase 11N approval credential") from exc
        if (
            not all((self.credential_id, self.principal_id, self.role)) or len(key) != 32
            or not all(_utc(value) for value in (self.valid_from, self.valid_until))
            or self.valid_from >= self.valid_until
        ):
            raise ValueError("invalid Phase 11N approval credential")


@dataclass(frozen=True, slots=True)
class VerifierApprovalRequest:
    request_id: str
    receipt_bound_assessment_id: str
    receipt_bound_assessment_hash: str
    governance_assessment_id: str
    verification_receipt_ids: tuple[str, ...]
    verification_receipt_hashes: tuple[str, ...]
    requested_at: datetime
    valid_from: datetime
    valid_until: datetime
    required_roles: tuple[str, ...]
    request_hash: str
    config_hash: str
    version: str = VERSION
    broker_write_authorized: bool = field(default=False, init=False)
    cohort_activation_authorized: bool = field(default=False, init=False)
    live_trading_authorized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        times = (self.requested_at, self.valid_from, self.valid_until)
        if (
            not all((self.request_id, self.receipt_bound_assessment_id,
                     self.governance_assessment_id))
            or not all(_sha(value) for value in (
                self.receipt_bound_assessment_hash, self.request_hash, self.config_hash,
            ))
            or self.verification_receipt_ids
            != tuple(sorted(set(self.verification_receipt_ids)))
            or not all(self.verification_receipt_ids)
            or len(self.verification_receipt_ids) != len(self.verification_receipt_hashes)
            or not self.verification_receipt_ids
            or not all(_sha(value) for value in self.verification_receipt_hashes)
            or not all(_utc(value) for value in times)
            or not self.requested_at <= self.valid_from < self.valid_until
            or not self.required_roles
            or not all(self.required_roles)
            or self.required_roles != tuple(sorted(set(self.required_roles)))
            or self.version != VERSION
        ):
            raise ValueError("invalid Phase 11N approval request")


@dataclass(frozen=True, slots=True)
class VerifierApprovalAttestation:
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
            raise ValueError("invalid Phase 11N approval attestation") from exc
        if (
            not all((self.attestation_id, self.request_id, self.credential_id,
                     self.principal_id, self.role))
            or not _sha(self.request_hash) or not _utc(self.signed_at) or len(signature) != 64
        ):
            raise ValueError("invalid Phase 11N approval attestation")


@dataclass(frozen=True, slots=True)
class VerifierApprovalAssessment:
    assessment_id: str
    request_id: str
    receipt_bound_assessment_id: str
    evaluated_at: datetime
    state: VerifierApprovalState
    verified_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    request_hash: str
    config_hash: str
    version: str = VERSION
    provider_approved: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    qualifying_trade: bool = field(default=False, init=False)
    cohort_activated: bool = field(default=False, init=False)
    live_trading_enabled: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.request_id, self.receipt_bound_assessment_id))
            or not _utc(self.evaluated_at) or not _sha(self.request_hash)
            or not _sha(self.config_hash)
            or self.verified_roles != tuple(sorted(set(self.verified_roles)))
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or self.version != VERSION
        ):
            raise ValueError("invalid Phase 11N approval assessment")


def load_verifier_approval_config(path: str | Path) -> VerifierApprovalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"approval_version", "mode", "policy", "authority"}:
        raise ValueError("Phase 11N configuration keys are invalid")
    if raw["approval_version"] != VERSION or raw["mode"] != "OFFLINE_SIGNED_BUNDLE_APPROVAL":
        raise ValueError("Phase 11N mode is invalid")
    if raw["policy"] != {
        "approval_roles_operator_supplied": True, "distinct_principals": True,
        "signature_algorithm": "Ed25519", "exact_receipt_bundle_scope": True,
        "bounded_validity_window": True,
    }:
        raise ValueError("Phase 11N policy is invalid")
    authority = raw["authority"]
    expected = {
        "provider_approval_enabled", "network_enabled", "key_generation_enabled",
        "key_loading_enabled", "broker_writes_enabled", "qualifying_trade_enabled",
        "cohort_activation_enabled", "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict) or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise ValueError("Phase 11N authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return VerifierApprovalConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_verifier_approval_credential(
    *, principal_id: str, role: str, public_key: bytes,
    valid_from: datetime, valid_until: datetime,
) -> VerifierApprovalCredential:
    encoded = base64.b64encode(public_key).decode()
    identity = (principal_id, role, encoded, valid_from, valid_until)
    return VerifierApprovalCredential(
        deterministic_id("prospective_verifier_approval_credential", identity),
        principal_id, role, encoded, valid_from, valid_until,
    )


def build_verifier_approval_request(
    config: VerifierApprovalConfig, bound: ReceiptBoundGovernanceAssessment, *,
    requested_at: datetime, valid_from: datetime, valid_until: datetime,
    required_roles: tuple[str, ...],
) -> VerifierApprovalRequest:
    roles = tuple(sorted(required_roles))
    content = (
        bound.assessment_id, canonical_hash(bound), bound.governance_assessment_id,
        bound.verification_receipt_ids, bound.verification_receipt_hashes,
        requested_at, valid_from, valid_until, roles, config.config_hash,
    )
    return VerifierApprovalRequest(
        deterministic_id("prospective_verifier_approval_request", content),
        bound.assessment_id, canonical_hash(bound), bound.governance_assessment_id,
        bound.verification_receipt_ids, bound.verification_receipt_hashes,
        requested_at, valid_from, valid_until, roles, canonical_hash(content), config.config_hash,
    )


def verifier_approval_message(
    request: VerifierApprovalRequest, credential: VerifierApprovalCredential,
    signed_at: datetime,
) -> bytes:
    return canonical_json((
        request.request_id, request.request_hash, request.receipt_bound_assessment_id,
        request.receipt_bound_assessment_hash, request.governance_assessment_id,
        request.verification_receipt_ids, request.verification_receipt_hashes,
        request.valid_from, request.valid_until, credential.credential_id,
        credential.principal_id, credential.role, signed_at,
    )).encode()


def build_verifier_approval_attestation(
    request: VerifierApprovalRequest, credential: VerifierApprovalCredential, *,
    signed_at: datetime, signature: bytes,
) -> VerifierApprovalAttestation:
    encoded = base64.b64encode(signature).decode()
    identity = (
        request.request_id, request.request_hash, credential.credential_id,
        credential.principal_id, credential.role, signed_at, encoded,
    )
    return VerifierApprovalAttestation(
        deterministic_id("prospective_verifier_approval_attestation", identity),
        request.request_id, request.request_hash, credential.credential_id,
        credential.principal_id, credential.role, signed_at, encoded,
    )


def evaluate_verifier_approval(
    request: VerifierApprovalRequest, *,
    credentials: tuple[VerifierApprovalCredential, ...],
    attestations: tuple[VerifierApprovalAttestation, ...], evaluated_at: datetime,
) -> VerifierApprovalAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 11N evaluation time must be UTC")
    by_id = {item.credential_id: item for item in credentials}
    if len(by_id) != len(credentials):
        raise ValueError("Phase 11N credential identities must be unique")
    reasons: set[str] = set()
    verified: dict[str, str] = {}
    if not request.valid_from <= evaluated_at < request.valid_until:
        reasons.add("REQUEST_OUTSIDE_VALIDITY_WINDOW")
    for attestation in sorted(attestations, key=lambda item: (item.role, item.attestation_id)):
        credential = by_id.get(attestation.credential_id)
        if (
            credential is None or attestation.request_id != request.request_id
            or attestation.request_hash != request.request_hash
            or attestation.principal_id != credential.principal_id
            or attestation.role != credential.role or attestation.role not in request.required_roles
            or not credential.valid_from <= attestation.signed_at < credential.valid_until
            or not request.valid_from <= attestation.signed_at < request.valid_until
            or attestation.signed_at > evaluated_at
        ):
            reasons.add("INVALID_APPROVAL_ATTESTATION")
            continue
        try:
            Ed25519PublicKey.from_public_bytes(
                base64.b64decode(credential.public_key_base64, validate=True)
            ).verify(
                base64.b64decode(attestation.signature_base64, validate=True),
                verifier_approval_message(request, credential, attestation.signed_at),
            )
        except (InvalidSignature, ValueError):
            reasons.add("INVALID_APPROVAL_ATTESTATION")
            continue
        if attestation.role in verified or attestation.principal_id in verified.values():
            reasons.add("APPROVER_SEPARATION_FAILURE")
            continue
        verified[attestation.role] = attestation.principal_id
    if set(request.required_roles) - set(verified):
        reasons.add("REQUIRED_APPROVAL_MISSING")
    hard = {
        "INVALID_APPROVAL_ATTESTATION", "APPROVER_SEPARATION_FAILURE",
        "REQUEST_OUTSIDE_VALIDITY_WINDOW",
    }
    state = (
        VerifierApprovalState.BLOCKED if reasons & hard else VerifierApprovalState.INCOMPLETE
        if reasons else VerifierApprovalState.APPROVED
    )
    roles, reason_codes = tuple(sorted(verified)), tuple(sorted(reasons))
    identity = (request.request_id, evaluated_at, state, roles, reason_codes, request.request_hash)
    return VerifierApprovalAssessment(
        deterministic_id("prospective_verifier_approval_assessment", identity),
        request.request_id, request.receipt_bound_assessment_id, evaluated_at, state, roles,
        reason_codes, request.request_hash, request.config_hash,
    )


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _sha(value: str) -> bool:
    return (
        len(value) == 71 and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
