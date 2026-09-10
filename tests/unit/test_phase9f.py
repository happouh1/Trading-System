from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper.certification import CertificationAssessment, CertificationState
from trading_system.paper.rollout import (
    StagedRolloutPlan,
    build_rollout_stage,
    build_staged_rollout_plan,
    load_paper_rollout_config,
)
from trading_system.paper.sandbox_lease import (
    SandboxLeaseConfig,
    SandboxLeaseConfigError,
    SandboxLeaseState,
    SandboxStageLease,
    build_sandbox_lease_revocation,
    build_sandbox_stage_lease,
    evaluate_sandbox_lease,
    load_sandbox_lease_config,
)
from trading_system.paper.stage_authorization import (
    StageAuthorizationAssessment,
    StageAuthorizationState,
)

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 9, 10, 14, tzinfo=UTC)


def _inputs() -> tuple[SandboxLeaseConfig, StageAuthorizationAssessment, StagedRolloutPlan]:
    certification = CertificationAssessment(
        "certification", "dossier", NOW - timedelta(days=1),
        CertificationState.REVIEW_READY, ("REVIEWER",), (),
        "sha256:dossier", "sha256:certification-config",
    )
    rollout_config = load_paper_rollout_config(ROOT / "config/paper.phase9d.v1.yaml")
    stage = build_rollout_stage(
        stage_id="OBSERVE", sequence=1, capital_ceiling=Decimal("1000"),
        position_ceiling=1, minimum_observations=10,
        rollback_trigger_codes=("HALT",),
    )
    plan = build_staged_rollout_plan(
        rollout_config, certification=certification, session_id="paper-9f",
        declared_at=NOW - timedelta(hours=2), stages=(stage,),
    )
    authorization = StageAuthorizationAssessment(
        "authorization", "request", plan.plan_id, stage.stage_id,
        NOW - timedelta(hours=1), StageAuthorizationState.SIGNATURES_VERIFIED,
        ("REVIEWER",), (), "sha256:request", "sha256:authorization-config",
    )
    config = load_sandbox_lease_config(ROOT / "config/paper.phase9f.v1.yaml")
    return config, authorization, plan


def _lease() -> SandboxStageLease:
    config, authorization, plan = _inputs()
    return build_sandbox_stage_lease(
        config, authorization=authorization, plan=plan, issued_at=NOW,
        valid_from=NOW + timedelta(minutes=5), valid_until=NOW + timedelta(hours=1),
    )


def test_lease_inherits_limits_and_grants_no_execution_authority() -> None:
    lease = _lease()
    assert lease.capital_ceiling == Decimal("1000")
    assert lease.position_ceiling == 1
    assert not lease.process_launch_authorized
    assert not lease.network_authorized
    assert not lease.broker_write_authorized
    assert not lease.sandbox_execution_authorized
    assert not lease.live_trading_authorized


def test_lease_lifecycle_is_causal_and_read_only() -> None:
    lease = _lease()
    scheduled = evaluate_sandbox_lease(lease, evaluated_at=NOW + timedelta(minutes=1))
    assert scheduled.state is SandboxLeaseState.SCHEDULED
    opened = evaluate_sandbox_lease(lease, evaluated_at=NOW + timedelta(minutes=10))
    assert opened.state is SandboxLeaseState.SUPERVISION_WINDOW_OPEN
    assert not opened.sandbox_execution_enabled
    expired = evaluate_sandbox_lease(lease, evaluated_at=NOW + timedelta(hours=1))
    assert expired.state is SandboxLeaseState.EXPIRED


def test_revocation_is_immediate_and_future_revocation_is_rejected() -> None:
    lease = _lease()
    revocation = build_sandbox_lease_revocation(
        lease, revoked_at=NOW + timedelta(minutes=20), reason_code="OPERATOR_HALT"
    )
    with pytest.raises(ValueError, match="causally"):
        evaluate_sandbox_lease(
            lease, evaluated_at=NOW + timedelta(minutes=10), revocation=revocation
        )
    revoked = evaluate_sandbox_lease(
        lease, evaluated_at=NOW + timedelta(minutes=20), revocation=revocation
    )
    assert revoked.state is SandboxLeaseState.REVOKED
    assert not revoked.broker_write_performed


def test_lease_requires_verified_exact_stage_authorization() -> None:
    lease = _lease()
    config, authorization, plan = _inputs()
    with pytest.raises(ValueError, match="verified signatures"):
        build_sandbox_stage_lease(
            config,
            authorization=replace(
                authorization, state=StageAuthorizationState.INCOMPLETE
            ),
            plan=plan,
            issued_at=NOW,
            valid_from=NOW + timedelta(minutes=5),
            valid_until=NOW + timedelta(hours=1),
        )
    with pytest.raises(ValueError, match="scope"):
        build_sandbox_stage_lease(
            config,
            authorization=replace(authorization, stage_id="OTHER"),
            plan=plan,
            issued_at=NOW,
            valid_from=NOW + timedelta(minutes=5),
            valid_until=NOW + timedelta(hours=1),
        )
    # Constructors remain strict even when callers try to widen authority manually.
    with pytest.raises(ValueError, match="sandbox supervision lease"):
        SandboxStageLease(
            lease.lease_id, lease.session_id, lease.authorization_assessment_id,
            lease.authorization_assessment_hash, lease.plan_id, lease.plan_hash,
            lease.stage_id, lease.issued_at, lease.valid_from, lease.valid_until,
            lease.capital_ceiling, lease.position_ceiling, lease.lease_hash,
            lease.config_hash, sandbox_execution_authorized=True,
        )


def test_config_rejects_execution_authority(tmp_path: Path) -> None:
    source = ROOT / "config/paper.phase9f.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["sandbox_execution_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SandboxLeaseConfigError, match="authority"):
        load_sandbox_lease_config(unsafe)
