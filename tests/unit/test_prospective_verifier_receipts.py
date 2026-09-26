from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from tests.unit.test_prospective_credential_governance import CONFIG, governed_inputs
from tests.unit.test_prospective_evidence_review import review_inputs
from trading_system.execution_sim.prospective_credential_governance import (
    CredentialIssuance,
    GovernanceState,
    TrustedTimestampEvidence,
    build_credential_revocation,
    load_credential_governance_config,
)
from trading_system.execution_sim.prospective_evidence_review import (
    EvidenceReviewAttestation,
    EvidenceReviewCredential,
    evaluate_evidence_review,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ExternalVerificationReceipt,
    evaluate_receipt_bound_governance,
    verify_credential_issuance,
    verify_credential_revocation,
    verify_trusted_timestamp,
)
from trading_system.serialization import canonical_hash


def verifier_inputs(
    credentials: tuple[EvidenceReviewCredential, ...],
    attestations: tuple[EvidenceReviewAttestation, ...],
    issuances: tuple[CredentialIssuance, ...],
    timestamps: tuple[TrustedTimestampEvidence, ...],
    now: datetime,
) -> tuple[ExternalVerificationReceipt, ...]:
    receipts = [
        verify_credential_issuance(
            issuance, credential, verifier_id="issuer-verifier",
            verifier_version="issuer-v1", verified_at=now + timedelta(minutes=2),
            verifier=lambda item, key: item.external_proof == "issuer-proof",
        )
        for issuance, credential in zip(issuances, credentials, strict=True)
    ]
    receipts.extend(
        verify_trusted_timestamp(
            timestamp, attestation, verifier_id="timestamp-verifier",
            verifier_version="timestamp-v1", verified_at=now + timedelta(minutes=2),
            verifier=lambda item, signature: item.token == "timestamp-token",
        )
        for timestamp, attestation in zip(timestamps, attestations, strict=True)
    )
    return tuple(receipts)


def test_receipts_reproduce_governance_without_new_authority() -> None:
    original, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    governance, bound = evaluate_receipt_bound_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(), timestamps=timestamps,
        verification_receipts=verifier_inputs(
            credentials, attestations, issuances, timestamps, now,
        ), evaluated_at=now + timedelta(minutes=3),
    )
    assert governance == original
    assert bound.state is GovernanceState.VERIFIED
    assert not bound.external_provider_selected and not bound.broker_write_performed
    assert not bound.qualifying_trade and not bound.cohort_activated


def test_rejected_timestamp_receipt_blocks_governance() -> None:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    receipts = list(verifier_inputs(credentials, attestations, issuances, timestamps, now))
    receipts[-1] = verify_trusted_timestamp(
        timestamps[-1], attestations[-1], verifier_id="timestamp-verifier",
        verifier_version="timestamp-v1", verified_at=now + timedelta(minutes=2),
        verifier=lambda item, signature: False,
    )
    governance, bound = evaluate_receipt_bound_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(), timestamps=timestamps,
        verification_receipts=tuple(receipts), evaluated_at=now + timedelta(minutes=3),
    )
    assert governance.state is GovernanceState.BLOCKED
    assert bound.state is GovernanceState.BLOCKED
    assert "TRUSTED_TIMESTAMP_INVALID" in governance.reason_codes


def test_missing_or_changed_receipt_fails_closed() -> None:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    receipts = verifier_inputs(credentials, attestations, issuances, timestamps, now)
    with pytest.raises(ValueError, match="exactly cover"):
        evaluate_receipt_bound_governance(
            load_credential_governance_config(CONFIG), review, credentials=credentials,
            attestations=attestations, issuances=issuances, revocations=(),
            timestamps=timestamps, verification_receipts=receipts[:-1],
            evaluated_at=now + timedelta(minutes=3),
        )
    changed = replace(receipts[0], proof_hash=canonical_hash("changed-proof"))
    with pytest.raises(ValueError, match="changed or unavailable"):
        evaluate_receipt_bound_governance(
            load_credential_governance_config(CONFIG), review, credentials=credentials,
            attestations=attestations, issuances=issuances, revocations=(),
            timestamps=timestamps, verification_receipts=(changed, *receipts[1:]),
            evaluated_at=now + timedelta(minutes=3),
        )


def test_revocation_verifier_outcome_is_recorded() -> None:
    _, credentials, _, issuances, _, now = governed_inputs()
    revocation = build_credential_revocation(
        credentials[0], issuer_id="external-issuer", revoked_at=now + timedelta(minutes=2),
        reason_code="KEY_COMPROMISE", external_proof="revocation-proof",
    )
    receipt = verify_credential_revocation(
        revocation, issuances[0], verifier_id="revocation-verifier",
        verifier_version="revocation-v1", verified_at=now + timedelta(minutes=2),
        verifier=lambda item, issuance: True,
    )
    assert receipt.accepted and receipt.reason_code == "VERIFIED"
