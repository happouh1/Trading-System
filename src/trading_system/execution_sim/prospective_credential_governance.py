"""External-verifier boundary for Phase 11K credential governance."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.execution_sim.prospective_evidence_review import (
    EvidenceReviewAssessment,
    EvidenceReviewAttestation,
    EvidenceReviewCredential,
    EvidenceReviewState,
)
from trading_system.serialization import canonical_hash, deterministic_id

VERSION = "11L.1.0"
TrustVerifier = Callable[["CredentialIssuance", EvidenceReviewCredential], bool]
RevocationVerifier = Callable[["CredentialRevocation", "CredentialIssuance"], bool]
TimestampVerifier = Callable[["TrustedTimestampEvidence", EvidenceReviewAttestation], bool]


class GovernanceState(StrEnum):
    VERIFIED = "VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CredentialGovernanceConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class CredentialIssuance:
    issuance_id: str
    issuer_id: str
    credential_id: str
    credential_hash: str
    issued_at: datetime
    supersedes_credential_id: str | None
    external_proof: str

    def __post_init__(self) -> None:
        if (
            not all((self.issuance_id, self.issuer_id, self.credential_id, self.external_proof))
            or not _sha(self.credential_hash)
            or not _utc(self.issued_at)
            or self.supersedes_credential_id == self.credential_id
        ):
            raise ValueError("invalid Phase 11L credential issuance")


@dataclass(frozen=True, slots=True)
class CredentialRevocation:
    revocation_id: str
    issuer_id: str
    credential_id: str
    credential_hash: str
    revoked_at: datetime
    reason_code: str
    external_proof: str

    def __post_init__(self) -> None:
        if (
            not all((self.revocation_id, self.issuer_id, self.credential_id,
                     self.reason_code, self.external_proof))
            or not _sha(self.credential_hash)
            or not _utc(self.revoked_at)
        ):
            raise ValueError("invalid Phase 11L credential revocation")


@dataclass(frozen=True, slots=True)
class TrustedTimestampEvidence:
    timestamp_id: str
    provider_id: str
    attestation_id: str
    attestation_hash: str
    timestamped_at: datetime
    received_at: datetime
    token: str

    def __post_init__(self) -> None:
        if (
            not all((self.timestamp_id, self.provider_id, self.attestation_id, self.token))
            or not _sha(self.attestation_hash)
            or not all(_utc(value) for value in (self.timestamped_at, self.received_at))
            or self.timestamped_at > self.received_at
        ):
            raise ValueError("invalid Phase 11L timestamp evidence")


@dataclass(frozen=True, slots=True)
class GovernedReviewAssessment:
    assessment_id: str
    review_assessment_id: str
    evaluated_at: datetime
    state: GovernanceState
    verified_credentials: tuple[str, ...]
    timestamp_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    config_hash: str
    version: str = VERSION
    external_verifiers_used: bool = True
    broker_write_performed: bool = field(default=False, init=False)
    qualifying_trade: bool = field(default=False, init=False)
    cohort_activated: bool = field(default=False, init=False)
    live_trading_enabled: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.review_assessment_id))
            or not _utc(self.evaluated_at)
            or not _sha(self.config_hash)
            or self.verified_credentials != tuple(sorted(set(self.verified_credentials)))
            or self.timestamp_ids != tuple(sorted(set(self.timestamp_ids)))
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or self.version != VERSION
            or not self.external_verifiers_used
        ):
            raise ValueError("invalid Phase 11L governance assessment")


def load_credential_governance_config(path: str | Path) -> CredentialGovernanceConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or set(raw) != {"governance_version", "mode", "policy", "authority"}
    ):
        raise ValueError("Phase 11L configuration keys are invalid")
    if raw["governance_version"] != VERSION or raw["mode"] != "EXTERNAL_VERIFIER_BOUNDARY":
        raise ValueError("Phase 11L mode is invalid")
    if raw["policy"] != {
        "issuer_verifier_required": True,
        "revocation_verifier_required": True,
        "timestamp_verifier_required": True,
        "append_only_records": True,
        "causal_status_at_cutoff": True,
        "exact_phase_11k_scope": True,
    }:
        raise ValueError("Phase 11L policy is invalid")
    authority = raw["authority"]
    expected = {
        "verifier_implementation_bundled", "network_enabled", "key_generation_enabled",
        "key_loading_enabled", "broker_writes_enabled", "qualifying_trade_enabled",
        "cohort_activation_enabled", "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise ValueError("Phase 11L authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return CredentialGovernanceConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_credential_issuance(
    credential: EvidenceReviewCredential, *, issuer_id: str, issued_at: datetime,
    external_proof: str, supersedes_credential_id: str | None = None,
) -> CredentialIssuance:
    content = (
        issuer_id, credential.credential_id, canonical_hash(credential), issued_at,
        supersedes_credential_id, external_proof,
    )
    return CredentialIssuance(
        deterministic_id("prospective_credential_issuance", content), issuer_id,
        credential.credential_id, canonical_hash(credential), issued_at,
        supersedes_credential_id, external_proof,
    )


def build_credential_revocation(
    credential: EvidenceReviewCredential, *, issuer_id: str, revoked_at: datetime,
    reason_code: str, external_proof: str,
) -> CredentialRevocation:
    content = (
        issuer_id, credential.credential_id, canonical_hash(credential), revoked_at,
        reason_code, external_proof,
    )
    return CredentialRevocation(
        deterministic_id("prospective_credential_revocation", content), issuer_id,
        credential.credential_id, canonical_hash(credential), revoked_at, reason_code,
        external_proof,
    )


def build_trusted_timestamp(
    attestation: EvidenceReviewAttestation, *, provider_id: str,
    timestamped_at: datetime, received_at: datetime, token: str,
) -> TrustedTimestampEvidence:
    content = (
        provider_id, attestation.attestation_id, canonical_hash(attestation),
        timestamped_at, received_at, token,
    )
    return TrustedTimestampEvidence(
        deterministic_id("prospective_review_timestamp", content), provider_id,
        attestation.attestation_id, canonical_hash(attestation), timestamped_at, received_at,
        token,
    )


def evaluate_credential_governance(
    config: CredentialGovernanceConfig, review: EvidenceReviewAssessment, *,
    credentials: tuple[EvidenceReviewCredential, ...],
    attestations: tuple[EvidenceReviewAttestation, ...],
    issuances: tuple[CredentialIssuance, ...],
    revocations: tuple[CredentialRevocation, ...],
    timestamps: tuple[TrustedTimestampEvidence, ...], trust_verifier: TrustVerifier,
    revocation_verifier: RevocationVerifier, timestamp_verifier: TimestampVerifier,
    evaluated_at: datetime,
) -> GovernedReviewAssessment:
    if not _utc(evaluated_at):
        raise ValueError("Phase 11L evaluation time must be UTC")
    reasons: set[str] = set()
    if review.state is not EvidenceReviewState.SIGNATURES_VERIFIED:
        reasons.add("REVIEW_SIGNATURES_NOT_VERIFIED")
    by_credential = {item.credential_id: item for item in credentials}
    by_attestation = {item.attestation_id: item for item in attestations}
    by_issuance = {item.credential_id: item for item in issuances}
    by_timestamp = {item.attestation_id: item for item in timestamps}
    if any((
        len(by_credential) != len(credentials), len(by_attestation) != len(attestations),
        len(by_issuance) != len(issuances), len(by_timestamp) != len(timestamps),
    )):
        reasons.add("DUPLICATE_GOVERNANCE_IDENTITY")
    if tuple(sorted(item.role for item in attestations)) != review.verified_roles:
        reasons.add("REVIEW_SCOPE_MISMATCH")

    trusted_issuances: dict[str, CredentialIssuance] = {}
    for issuance_record in issuances:
        credential = by_credential.get(issuance_record.credential_id)
        if (
            credential is None
            or issuance_record.credential_hash != canonical_hash(credential)
            or issuance_record.issued_at > evaluated_at
            or not trust_verifier(issuance_record, credential)
        ):
            reasons.add("CREDENTIAL_TRUST_INVALID")
        else:
            trusted_issuances[issuance_record.credential_id] = issuance_record

    trusted_revocations: set[str] = set()
    for revocation in revocations:
        found_issuance = trusted_issuances.get(revocation.credential_id)
        if (
            found_issuance is None
            or revocation.issuer_id != found_issuance.issuer_id
            or revocation.credential_hash != found_issuance.credential_hash
            or revocation.revoked_at < found_issuance.issued_at
            or revocation.revoked_at > evaluated_at
            or not revocation_verifier(revocation, found_issuance)
        ):
            reasons.add("REVOCATION_EVIDENCE_INVALID")
        else:
            trusted_revocations.add(revocation.credential_id)

    superseded = {
        issuance.supersedes_credential_id for issuance in trusted_issuances.values()
        if issuance.supersedes_credential_id is not None and issuance.issued_at <= evaluated_at
    }
    verified_credentials: list[str] = []
    verified_timestamps: list[str] = []
    for attestation in sorted(attestations, key=lambda item: item.attestation_id):
        credential = by_credential.get(attestation.credential_id)
        found_issuance = trusted_issuances.get(attestation.credential_id)
        timestamp = by_timestamp.get(attestation.attestation_id)
        if credential is None or found_issuance is None or timestamp is None:
            reasons.add("GOVERNANCE_EVIDENCE_MISSING")
            continue
        if found_issuance.issued_at > attestation.signed_at:
            reasons.add("CREDENTIAL_NOT_ISSUED_AT_SIGNING")
            continue
        if credential.credential_id in superseded:
            reasons.add("CREDENTIAL_SUPERSEDED")
            continue
        if credential.credential_id in trusted_revocations:
            reasons.add("CREDENTIAL_REVOKED")
            continue
        if (
            timestamp.attestation_hash != canonical_hash(attestation)
            or not attestation.signed_at <= timestamp.timestamped_at <= timestamp.received_at
            or timestamp.received_at > evaluated_at
            or not timestamp_verifier(timestamp, attestation)
        ):
            reasons.add("TRUSTED_TIMESTAMP_INVALID")
            continue
        verified_credentials.append(credential.credential_id)
        verified_timestamps.append(timestamp.timestamp_id)
    if len(verified_credentials) != len(review.verified_roles):
        reasons.add("VERIFIED_ROLE_GOVERNANCE_INCOMPLETE")
    hard = {
        "CREDENTIAL_TRUST_INVALID", "REVOCATION_EVIDENCE_INVALID", "CREDENTIAL_REVOKED",
        "CREDENTIAL_SUPERSEDED", "CREDENTIAL_NOT_ISSUED_AT_SIGNING",
        "TRUSTED_TIMESTAMP_INVALID", "DUPLICATE_GOVERNANCE_IDENTITY",
        "REVIEW_SCOPE_MISMATCH",
    }
    state = (
        GovernanceState.BLOCKED if reasons & hard else GovernanceState.INCOMPLETE
        if reasons else GovernanceState.VERIFIED
    )
    credential_ids = tuple(sorted(verified_credentials))
    timestamp_ids = tuple(sorted(verified_timestamps))
    reason_codes = tuple(sorted(reasons))
    identity = (
        review.assessment_id, evaluated_at, state, credential_ids, timestamp_ids,
        reason_codes, config.config_hash,
    )
    return GovernedReviewAssessment(
        deterministic_id("prospective_credential_governance", identity), review.assessment_id,
        evaluated_at, state, credential_ids, timestamp_ids, reason_codes, config.config_hash,
    )


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _sha(value: str) -> bool:
    return (
        len(value) == 71 and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
