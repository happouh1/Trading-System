from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.unit.test_prospective_credential_governance import CONFIG, governed_inputs
from tests.unit.test_prospective_evidence_review import review_inputs
from tests.unit.test_prospective_verifier_receipts import verifier_inputs
from trading_system.execution_sim.prospective_credential_governance import (
    load_credential_governance_config,
)
from trading_system.execution_sim.prospective_evidence_review import evaluate_evidence_review
from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAttestation,
    VerifierApprovalCredential,
    VerifierApprovalRequest,
    VerifierApprovalState,
    build_verifier_approval_attestation,
    build_verifier_approval_credential,
    build_verifier_approval_request,
    evaluate_verifier_approval,
    load_verifier_approval_config,
    verifier_approval_message,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
    evaluate_receipt_bound_governance,
)

ROOT = Path(__file__).parents[2]
APPROVAL_CONFIG = ROOT / "config/prospective_verifier_approval.v1.yaml"


def approval_inputs() -> tuple[ReceiptBoundGovernanceAssessment, datetime]:
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    _, bound = evaluate_receipt_bound_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(),
        timestamps=timestamps,
        verification_receipts=verifier_inputs(
            credentials, attestations, issuances, timestamps, now,
        ),
        evaluated_at=now + timedelta(minutes=3),
    )
    return bound, now


def signed_approval(
    bound: ReceiptBoundGovernanceAssessment, now: datetime,
) -> tuple[
    VerifierApprovalRequest,
    tuple[VerifierApprovalCredential, ...],
    tuple[VerifierApprovalAttestation, ...],
]:
    request = build_verifier_approval_request(
        load_verifier_approval_config(APPROVAL_CONFIG), bound,
        requested_at=now + timedelta(minutes=3), valid_from=now + timedelta(minutes=3),
        valid_until=now + timedelta(hours=2),
        required_roles=("RISK_APPROVER", "SYSTEM_APPROVER"),
    )
    credentials = []
    attestations = []
    for principal, role in (("alice", "RISK_APPROVER"), ("bob", "SYSTEM_APPROVER")):
        private = Ed25519PrivateKey.generate()
        credential = build_verifier_approval_credential(
            principal_id=principal, role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=now, valid_until=now + timedelta(days=1),
        )
        signed_at = now + timedelta(minutes=4)
        attestation = build_verifier_approval_attestation(
            request, credential, signed_at=signed_at,
            signature=private.sign(
                verifier_approval_message(request, credential, signed_at)
            ),
        )
        credentials.append(credential)
        attestations.append(attestation)
    return request, tuple(credentials), tuple(attestations)


def test_distinct_signed_roles_approve_exact_bundle_without_new_authority() -> None:
    bound, now = approval_inputs()
    request, credentials, attestations = signed_approval(bound, now)
    result = evaluate_verifier_approval(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=5),
    )
    assert result.state is VerifierApprovalState.APPROVED
    assert result.verified_roles == ("RISK_APPROVER", "SYSTEM_APPROVER")
    assert not result.provider_approved and not result.broker_write_performed
    assert not result.qualifying_trade and not result.cohort_activated
    assert not result.live_trading_enabled


def test_missing_role_is_incomplete_and_invalid_signature_is_blocked() -> None:
    bound, now = approval_inputs()
    request, credentials, attestations = signed_approval(bound, now)
    incomplete = evaluate_verifier_approval(
        request, credentials=credentials[:1], attestations=attestations[:1],
        evaluated_at=now + timedelta(minutes=5),
    )
    assert incomplete.state is VerifierApprovalState.INCOMPLETE
    invalid = replace(
        attestations[0], signature_base64=base64.b64encode(b"0" * 64).decode(),
    )
    blocked = evaluate_verifier_approval(
        request, credentials=credentials, attestations=(invalid, attestations[1]),
        evaluated_at=now + timedelta(minutes=5),
    )
    assert blocked.state is VerifierApprovalState.BLOCKED
    assert "INVALID_APPROVAL_ATTESTATION" in blocked.reason_codes


def test_changed_bundle_changes_request_and_rejects_old_attestations() -> None:
    bound, now = approval_inputs()
    request, credentials, attestations = signed_approval(bound, now)
    changed_bound = replace(bound, assessment_id=f"{bound.assessment_id}-changed")
    changed_request = build_verifier_approval_request(
        load_verifier_approval_config(APPROVAL_CONFIG), changed_bound,
        requested_at=now + timedelta(minutes=3), valid_from=now + timedelta(minutes=3),
        valid_until=now + timedelta(hours=2),
        required_roles=("RISK_APPROVER", "SYSTEM_APPROVER"),
    )
    assert changed_request.request_hash != request.request_hash
    result = evaluate_verifier_approval(
        changed_request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=5),
    )
    assert result.state is VerifierApprovalState.BLOCKED
