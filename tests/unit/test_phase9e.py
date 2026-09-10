from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.paper.rollout import RolloutGateAssessment, RolloutGateState
from trading_system.paper.stage_authorization import (
    StageAuthorizationConfigError,
    StageAuthorizationRequest,
    StageAuthorizationState,
    StageReviewAttestation,
    StageReviewCredential,
    build_stage_authorization_request,
    build_stage_review_attestation,
    build_stage_review_credential,
    evaluate_stage_authorization,
    load_stage_authorization_config,
    stage_review_message,
)

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 9, 9, 16, tzinfo=UTC)


def _rollout(state: RolloutGateState = RolloutGateState.READY_FOR_HUMAN_REVIEW) -> (
    RolloutGateAssessment
):
    return RolloutGateAssessment(
        "rollout-assessment", "rollout-plan", "OBSERVE", NOW, state, (),
        "sha256:evidence", "sha256:plan", "sha256:rollout-config",
    )


def _request() -> StageAuthorizationRequest:
    config = load_stage_authorization_config(ROOT / "config/paper.phase9e.v1.yaml")
    return build_stage_authorization_request(
        config, rollout_assessment=_rollout(), session_id="paper-9e",
        requested_at=NOW, valid_from=NOW + timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=2),
        required_review_roles=("RISK_REVIEWER", "OPERATIONS_REVIEWER"),
    )


def _signed(
    request: StageAuthorizationRequest,
) -> tuple[tuple[StageReviewCredential, ...], tuple[StageReviewAttestation, ...]]:
    credentials = []
    attestations = []
    signed_at = request.valid_from + timedelta(minutes=1)
    for role in request.required_review_roles:
        private = Ed25519PrivateKey.generate()
        credential = build_stage_review_credential(
            principal_id=f"principal-{role}", role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=NOW, valid_until=NOW + timedelta(days=1),
        )
        signature = private.sign(stage_review_message(request, credential, signed_at))
        credentials.append(credential)
        attestations.append(build_stage_review_attestation(
            request, credential, signed_at=signed_at, signature=signature
        ))
    return tuple(credentials), tuple(attestations)


def test_valid_signatures_are_verified_without_activation() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    assessment = evaluate_stage_authorization(
        request, credentials=credentials, attestations=tuple(reversed(attestations)),
        evaluated_at=NOW + timedelta(hours=1),
    )
    assert assessment.state is StageAuthorizationState.SIGNATURES_VERIFIED
    assert not assessment.stage_activated
    assert not assessment.deployment_performed
    assert not assessment.broker_write_performed
    assert not assessment.live_trading_enabled


def test_missing_bad_or_expired_signatures_do_not_verify() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    incomplete = evaluate_stage_authorization(
        request, credentials=credentials[:1], attestations=attestations[:1],
        evaluated_at=NOW + timedelta(hours=1),
    )
    assert incomplete.state is StageAuthorizationState.INCOMPLETE
    bad = build_stage_review_attestation(
        request, credentials[0], signed_at=request.valid_from + timedelta(minutes=1),
        signature=b"invalid",
    )
    blocked = evaluate_stage_authorization(
        request, credentials=credentials, attestations=(bad, attestations[1]),
        evaluated_at=NOW + timedelta(hours=1),
    )
    assert blocked.state is StageAuthorizationState.BLOCKED
    expired = evaluate_stage_authorization(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=request.valid_until,
    )
    assert expired.state is StageAuthorizationState.BLOCKED


def test_signature_is_bound_to_exact_stage_request() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    other = StageAuthorizationRequest(
        request.request_id, request.session_id, request.rollout_assessment_id,
        request.rollout_assessment_hash, request.plan_id, "LIMITED", request.requested_at,
        request.valid_from, request.valid_until, request.required_review_roles,
        request.request_hash, request.config_hash,
    )
    blocked = evaluate_stage_authorization(
        other, credentials=credentials, attestations=attestations,
        evaluated_at=NOW + timedelta(hours=1),
    )
    assert blocked.state is StageAuthorizationState.BLOCKED


def test_request_requires_review_ready_rollout_and_valid_window() -> None:
    config = load_stage_authorization_config(ROOT / "config/paper.phase9e.v1.yaml")
    with pytest.raises(ValueError, match="human-review-ready"):
        build_stage_authorization_request(
            config, rollout_assessment=_rollout(RolloutGateState.BLOCKED),
            session_id="paper-9e", requested_at=NOW, valid_from=NOW,
            valid_until=NOW + timedelta(hours=1), required_review_roles=("REVIEWER",),
        )
    with pytest.raises(ValueError, match="stage-review request"):
        build_stage_authorization_request(
            config, rollout_assessment=_rollout(), session_id="paper-9e",
            requested_at=NOW, valid_from=NOW - timedelta(minutes=1),
            valid_until=NOW + timedelta(hours=1), required_review_roles=("REVIEWER",),
        )


def test_config_rejects_activation_authority(tmp_path: Path) -> None:
    source = ROOT / "config/paper.phase9e.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["stage_activation_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(StageAuthorizationConfigError, match="authority"):
        load_stage_authorization_config(unsafe)
