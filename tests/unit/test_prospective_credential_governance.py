from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.unit.test_prospective_evidence_review import review_inputs
from trading_system.execution_sim.prospective_credential_governance import (
    CredentialIssuance,
    GovernanceState,
    GovernedReviewAssessment,
    TrustedTimestampEvidence,
    build_credential_issuance,
    build_credential_revocation,
    build_trusted_timestamp,
    evaluate_credential_governance,
    load_credential_governance_config,
)
from trading_system.execution_sim.prospective_evidence_review import (
    EvidenceReviewAttestation,
    EvidenceReviewCredential,
    build_evidence_review_attestation,
    build_evidence_review_credential,
    evaluate_evidence_review,
    evidence_review_message,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/prospective_credential_governance.v1.yaml"


def governed_inputs() -> tuple[
    GovernedReviewAssessment,
    tuple[EvidenceReviewCredential, ...],
    tuple[EvidenceReviewAttestation, ...],
    tuple[CredentialIssuance, ...],
    tuple[TrustedTimestampEvidence, ...],
    datetime,
]:
    request, now = review_inputs()
    credentials = []
    attestations = []
    issuances = []
    timestamps = []
    signed_at = now + timedelta(minutes=1)
    for principal, role in (("alice", "MARKET_REVIEWER"), ("bob", "PORTFOLIO_REVIEWER")):
        private = Ed25519PrivateKey.generate()
        credential = build_evidence_review_credential(
            principal_id=principal, role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=now - timedelta(hours=1), valid_until=now + timedelta(days=1),
        )
        attestation = build_evidence_review_attestation(
            request, credential, signed_at=signed_at,
            signature=private.sign(evidence_review_message(request, credential, signed_at)),
        )
        credentials.append(credential)
        attestations.append(attestation)
        issuances.append(build_credential_issuance(
            credential, issuer_id="external-issuer", issued_at=now - timedelta(hours=2),
            external_proof="issuer-proof",
        ))
        timestamps.append(build_trusted_timestamp(
            attestation, provider_id="external-tsa", timestamped_at=signed_at,
            received_at=signed_at + timedelta(seconds=1), token="timestamp-token",
        ))
    review = evaluate_evidence_review(
        request, credentials=tuple(credentials), attestations=tuple(attestations),
        evaluated_at=now + timedelta(minutes=2),
    )
    result = evaluate_credential_governance(
        load_credential_governance_config(CONFIG), review,
        credentials=tuple(credentials), attestations=tuple(attestations),
        issuances=tuple(issuances), revocations=(), timestamps=tuple(timestamps),
        trust_verifier=lambda issuance, credential: issuance.external_proof == "issuer-proof",
        revocation_verifier=lambda revocation, issuance: (
            revocation.external_proof == "revocation-proof"
        ),
        timestamp_verifier=lambda timestamp, attestation: (
            timestamp.token == "timestamp-token"
        ),
        evaluated_at=now + timedelta(minutes=3),
    )
    return (
        result, tuple(credentials), tuple(attestations), tuple(issuances), tuple(timestamps), now,
    )


def test_external_governance_verifies_without_granting_authority() -> None:
    result, credentials, _, _, timestamps, _ = governed_inputs()
    assert result.state is GovernanceState.VERIFIED
    assert result.verified_credentials == tuple(sorted(item.credential_id for item in credentials))
    assert result.timestamp_ids == tuple(sorted(item.timestamp_id for item in timestamps))
    assert not result.broker_write_performed and not result.cohort_activated


def test_missing_timestamp_is_incomplete() -> None:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    result = evaluate_credential_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(),
        timestamps=timestamps[:-1], trust_verifier=lambda issuance, credential: True,
        revocation_verifier=lambda revocation, issuance: True,
        timestamp_verifier=lambda timestamp, attestation: True,
        evaluated_at=now + timedelta(minutes=3),
    )
    assert result.state is GovernanceState.INCOMPLETE
    assert "GOVERNANCE_EVIDENCE_MISSING" in result.reason_codes


def test_verified_revocation_blocks_credential_immediately() -> None:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    revocation = build_credential_revocation(
        credentials[0], issuer_id="external-issuer", revoked_at=now + timedelta(minutes=2),
        reason_code="KEY_COMPROMISE", external_proof="revocation-proof",
    )
    result = evaluate_credential_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(revocation,),
        timestamps=timestamps, trust_verifier=lambda issuance, credential: True,
        revocation_verifier=lambda item, issuance: item.external_proof == "revocation-proof",
        timestamp_verifier=lambda timestamp, attestation: True,
        evaluated_at=now + timedelta(minutes=3),
    )
    assert result.state is GovernanceState.BLOCKED
    assert "CREDENTIAL_REVOKED" in result.reason_codes


def test_trusted_successor_blocks_superseded_credential() -> None:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    private = Ed25519PrivateKey.generate()
    successor = build_evidence_review_credential(
        principal_id="alice", role="MARKET_REVIEWER",
        public_key=private.public_key().public_bytes_raw(),
        valid_from=now + timedelta(minutes=2), valid_until=now + timedelta(days=1),
    )
    successor_issuance = build_credential_issuance(
        successor, issuer_id="external-issuer", issued_at=now + timedelta(minutes=2),
        external_proof="issuer-proof", supersedes_credential_id=credentials[0].credential_id,
    )
    result = evaluate_credential_governance(
        load_credential_governance_config(CONFIG), review,
        credentials=(*credentials, successor), attestations=attestations,
        issuances=(*issuances, successor_issuance), revocations=(), timestamps=timestamps,
        trust_verifier=lambda issuance, credential: True,
        revocation_verifier=lambda revocation, issuance: True,
        timestamp_verifier=lambda timestamp, attestation: True,
        evaluated_at=now + timedelta(minutes=3),
    )
    assert result.state is GovernanceState.BLOCKED
    assert "CREDENTIAL_SUPERSEDED" in result.reason_codes


def test_untrusted_revocation_and_timestamp_fail_closed() -> None:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    revocation = build_credential_revocation(
        credentials[0], issuer_id="external-issuer", revoked_at=now + timedelta(minutes=2),
        reason_code="KEY_COMPROMISE", external_proof="untrusted",
    )
    result = evaluate_credential_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(revocation,),
        timestamps=timestamps, trust_verifier=lambda issuance, credential: True,
        revocation_verifier=lambda item, issuance: False,
        timestamp_verifier=lambda timestamp, attestation: False,
        evaluated_at=now + timedelta(minutes=3),
    )
    assert result.state is GovernanceState.BLOCKED
    assert "REVOCATION_EVIDENCE_INVALID" in result.reason_codes
    assert "TRUSTED_TIMESTAMP_INVALID" in result.reason_codes
