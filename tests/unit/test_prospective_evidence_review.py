from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tests.unit.test_prospective_controls import inputs
from tests.unit.test_prospective_evidence import records
from trading_system.execution_sim.prospective_evidence import corroborate_prospective_inputs
from trading_system.execution_sim.prospective_evidence_review import (
    EvidenceReviewRequest,
    EvidenceReviewState,
    build_evidence_review_attestation,
    build_evidence_review_credential,
    build_evidence_review_request,
    evaluate_evidence_review,
    evidence_review_message,
    load_evidence_review_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/prospective_evidence_review.v1.yaml"


def review_inputs() -> tuple[EvidenceReviewRequest, datetime]:
    entry, assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    evidence = corroborate_prospective_inputs(
        entry=entry, entry_assessment=assessment,
        portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
        planned_hold_sessions=10,
    )
    now = assessment.known_at
    config = load_evidence_review_config(CONFIG)
    request = build_evidence_review_request(
        config, evidence, requested_at=now, valid_from=now,
        valid_until=now + timedelta(hours=2),
        required_review_roles=("MARKET_REVIEWER", "PORTFOLIO_REVIEWER"),
    )
    return request, now


def test_two_distinct_signed_roles_verify_without_granting_authority() -> None:
    request, now = review_inputs()
    credentials = []
    attestations = []
    for principal, role in (("alice", "MARKET_REVIEWER"), ("bob", "PORTFOLIO_REVIEWER")):
        private = Ed25519PrivateKey.generate()
        credential = build_evidence_review_credential(
            principal_id=principal, role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=now - timedelta(hours=1), valid_until=now + timedelta(days=1),
        )
        signed_at = now + timedelta(minutes=1)
        attestation = build_evidence_review_attestation(
            request, credential, signed_at=signed_at,
            signature=private.sign(evidence_review_message(request, credential, signed_at)),
        )
        credentials.append(credential)
        attestations.append(attestation)
    result = evaluate_evidence_review(
        request, credentials=tuple(credentials), attestations=tuple(attestations),
        evaluated_at=now + timedelta(minutes=2),
    )
    assert result.state is EvidenceReviewState.SIGNATURES_VERIFIED
    assert result.verified_roles == ("MARKET_REVIEWER", "PORTFOLIO_REVIEWER")
    assert not result.source_authenticity_verified
    assert not result.broker_write_performed and not result.cohort_activated


def test_missing_review_is_incomplete_and_bad_signature_is_blocked() -> None:
    request, now = review_inputs()
    missing = evaluate_evidence_review(
        request, credentials=(), attestations=(), evaluated_at=now + timedelta(minutes=2),
    )
    assert missing.state is EvidenceReviewState.INCOMPLETE
    private = Ed25519PrivateKey.generate()
    credential = build_evidence_review_credential(
        principal_id="alice", role="MARKET_REVIEWER",
        public_key=private.public_key().public_bytes_raw(),
        valid_from=now - timedelta(hours=1), valid_until=now + timedelta(days=1),
    )
    signed_at = now + timedelta(minutes=1)
    bad = build_evidence_review_attestation(
        request, credential, signed_at=signed_at, signature=b"0" * 64,
    )
    blocked = evaluate_evidence_review(
        request, credentials=(credential,), attestations=(bad,),
        evaluated_at=now + timedelta(minutes=2),
    )
    assert blocked.state is EvidenceReviewState.BLOCKED
    assert "INVALID_ATTESTATION" in blocked.reason_codes
