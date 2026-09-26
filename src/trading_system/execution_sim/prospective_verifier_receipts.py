"""Immutable audit receipts for Phase 11L external verifier callbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from trading_system.execution_sim.prospective_credential_governance import (
    CredentialGovernanceConfig,
    CredentialIssuance,
    CredentialRevocation,
    GovernanceState,
    GovernedReviewAssessment,
    TrustedTimestampEvidence,
    evaluate_credential_governance,
)
from trading_system.execution_sim.prospective_evidence_review import (
    EvidenceReviewAssessment,
    EvidenceReviewAttestation,
    EvidenceReviewCredential,
)
from trading_system.serialization import canonical_hash, deterministic_id

VERSION = "11M.1.0"


class VerificationKind(StrEnum):
    CREDENTIAL_ISSUANCE = "CREDENTIAL_ISSUANCE"
    CREDENTIAL_REVOCATION = "CREDENTIAL_REVOCATION"
    TRUSTED_TIMESTAMP = "TRUSTED_TIMESTAMP"


@dataclass(frozen=True, slots=True)
class ExternalVerificationReceipt:
    receipt_id: str
    kind: VerificationKind
    subject_id: str
    subject_hash: str
    proof_hash: str
    verifier_id: str
    verifier_version: str
    verified_at: datetime
    accepted: bool
    reason_code: str
    version: str = VERSION
    network_used: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not all((self.receipt_id, self.subject_id, self.verifier_id,
                     self.verifier_version, self.reason_code))
            or not _sha(self.subject_hash) or not _sha(self.proof_hash)
            or not _utc(self.verified_at) or self.version != VERSION
            or (self.accepted and self.reason_code != "VERIFIED")
            or (not self.accepted and self.reason_code == "VERIFIED")
        ):
            raise ValueError("invalid Phase 11M external verification receipt")


@dataclass(frozen=True, slots=True)
class ReceiptBoundGovernanceAssessment:
    assessment_id: str
    governance_assessment_id: str
    governance_assessment_hash: str
    review_assessment_id: str
    verification_receipt_ids: tuple[str, ...]
    verification_receipt_hashes: tuple[str, ...]
    evaluated_at: datetime
    state: GovernanceState
    config_hash: str
    version: str = VERSION
    external_provider_selected: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    qualifying_trade: bool = field(default=False, init=False)
    cohort_activated: bool = field(default=False, init=False)
    live_trading_enabled: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.governance_assessment_id,
                     self.review_assessment_id))
            or not _sha(self.governance_assessment_hash) or not _sha(self.config_hash)
            or not _utc(self.evaluated_at) or self.version != VERSION
            or not self.verification_receipt_ids
            or self.verification_receipt_ids != tuple(sorted(set(self.verification_receipt_ids)))
            or len(self.verification_receipt_ids) != len(self.verification_receipt_hashes)
            or not all(_sha(value) for value in self.verification_receipt_hashes)
        ):
            raise ValueError("invalid Phase 11M receipt-bound governance assessment")


def verify_credential_issuance(
    issuance: CredentialIssuance, credential: EvidenceReviewCredential, *,
    verifier_id: str, verifier_version: str, verified_at: datetime,
    verifier: Callable[[CredentialIssuance, EvidenceReviewCredential], bool],
) -> ExternalVerificationReceipt:
    return _receipt(
        VerificationKind.CREDENTIAL_ISSUANCE, issuance.issuance_id, issuance,
        issuance.external_proof, verifier_id, verifier_version, verified_at,
        verifier(issuance, credential), "ISSUER_PROOF_REJECTED",
    )


def verify_credential_revocation(
    revocation: CredentialRevocation, issuance: CredentialIssuance, *,
    verifier_id: str, verifier_version: str, verified_at: datetime,
    verifier: Callable[[CredentialRevocation, CredentialIssuance], bool],
) -> ExternalVerificationReceipt:
    return _receipt(
        VerificationKind.CREDENTIAL_REVOCATION, revocation.revocation_id, revocation,
        revocation.external_proof, verifier_id, verifier_version, verified_at,
        verifier(revocation, issuance), "REVOCATION_PROOF_REJECTED",
    )


def verify_trusted_timestamp(
    timestamp: TrustedTimestampEvidence, attestation: EvidenceReviewAttestation, *,
    verifier_id: str, verifier_version: str, verified_at: datetime,
    verifier: Callable[[TrustedTimestampEvidence, EvidenceReviewAttestation], bool],
) -> ExternalVerificationReceipt:
    return _receipt(
        VerificationKind.TRUSTED_TIMESTAMP, timestamp.timestamp_id, timestamp,
        timestamp.token, verifier_id, verifier_version, verified_at,
        verifier(timestamp, attestation), "TIMESTAMP_PROOF_REJECTED",
    )


def evaluate_receipt_bound_governance(
    config: CredentialGovernanceConfig, review: EvidenceReviewAssessment, *,
    credentials: tuple[EvidenceReviewCredential, ...],
    attestations: tuple[EvidenceReviewAttestation, ...],
    issuances: tuple[CredentialIssuance, ...], revocations: tuple[CredentialRevocation, ...],
    timestamps: tuple[TrustedTimestampEvidence, ...],
    verification_receipts: tuple[ExternalVerificationReceipt, ...],
    evaluated_at: datetime,
) -> tuple[GovernedReviewAssessment, ReceiptBoundGovernanceAssessment]:
    if not _utc(evaluated_at):
        raise ValueError("Phase 11M evaluation time must be UTC")
    subjects: dict[tuple[VerificationKind, str], object] = {}
    for kind, items in (
        (VerificationKind.CREDENTIAL_ISSUANCE, issuances),
        (VerificationKind.CREDENTIAL_REVOCATION, revocations),
        (VerificationKind.TRUSTED_TIMESTAMP, timestamps),
    ):
        for item in items:
            subject_identity = _subject_id(item)
            if (kind, subject_identity) in subjects:
                raise ValueError("Phase 11M subject identities must be unique")
            subjects[(kind, subject_identity)] = item
    receipts = {(item.kind, item.subject_id): item for item in verification_receipts}
    if len(receipts) != len(verification_receipts) or set(receipts) != set(subjects):
        raise ValueError("Phase 11M verification receipts must exactly cover governance subjects")
    for key, subject in subjects.items():
        receipt = receipts[key]
        if (
            receipt.subject_hash != canonical_hash(subject)
            or receipt.proof_hash != canonical_hash(_proof(subject))
            or receipt.verified_at > evaluated_at
        ):
            raise ValueError("Phase 11M verification receipt is changed or unavailable")

    def accepted(kind: VerificationKind, subject_id: str, subject: object) -> bool:
        receipt = receipts[(kind, subject_id)]
        return receipt.subject_hash == canonical_hash(subject) and receipt.accepted

    governance = evaluate_credential_governance(
        config, review, credentials=credentials, attestations=attestations,
        issuances=issuances, revocations=revocations, timestamps=timestamps,
        trust_verifier=lambda issuance, credential: accepted(
            VerificationKind.CREDENTIAL_ISSUANCE, issuance.issuance_id, issuance,
        ),
        revocation_verifier=lambda revocation, issuance: accepted(
            VerificationKind.CREDENTIAL_REVOCATION, revocation.revocation_id, revocation,
        ),
        timestamp_verifier=lambda timestamp, attestation: accepted(
            VerificationKind.TRUSTED_TIMESTAMP, timestamp.timestamp_id, timestamp,
        ),
        evaluated_at=evaluated_at,
    )
    ordered = tuple(sorted(verification_receipts, key=lambda item: item.receipt_id))
    receipt_ids = tuple(item.receipt_id for item in ordered)
    receipt_hashes = tuple(canonical_hash(item) for item in ordered)
    assessment_identity = (
        governance.assessment_id, canonical_hash(governance), review.assessment_id,
        receipt_ids, receipt_hashes, evaluated_at, governance.state, config.config_hash,
    )
    bound = ReceiptBoundGovernanceAssessment(
        deterministic_id("prospective_receipt_bound_governance", assessment_identity),
        governance.assessment_id, canonical_hash(governance), review.assessment_id,
        receipt_ids, receipt_hashes, evaluated_at, governance.state, config.config_hash,
    )
    return governance, bound


def _receipt(
    kind: VerificationKind, subject_id: str, subject: object, proof: str,
    verifier_id: str, verifier_version: str, verified_at: datetime, accepted: bool,
    rejection_reason: str,
) -> ExternalVerificationReceipt:
    if not _utc(verified_at) or not verifier_id or not verifier_version:
        raise ValueError("Phase 11M verifier metadata is invalid")
    subject_hash, proof_hash = canonical_hash(subject), canonical_hash(proof)
    reason = "VERIFIED" if accepted else rejection_reason
    identity = (
        kind, subject_id, subject_hash, proof_hash, verifier_id, verifier_version,
        verified_at, accepted, reason,
    )
    return ExternalVerificationReceipt(
        deterministic_id("prospective_external_verification", identity), kind, subject_id,
        subject_hash, proof_hash, verifier_id, verifier_version, verified_at, accepted, reason,
    )


def _subject_id(subject: object) -> str:
    if isinstance(subject, CredentialIssuance):
        return subject.issuance_id
    if isinstance(subject, CredentialRevocation):
        return subject.revocation_id
    if isinstance(subject, TrustedTimestampEvidence):
        return subject.timestamp_id
    raise TypeError("unsupported Phase 11M verification subject")


def _proof(subject: object) -> str:
    if isinstance(subject, (CredentialIssuance, CredentialRevocation)):
        return subject.external_proof
    if isinstance(subject, TrustedTimestampEvidence):
        return subject.token
    raise TypeError("unsupported Phase 11M verification subject")


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _sha(value: str) -> bool:
    return (
        len(value) == 71 and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
