from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper.certification import CertificationAssessment, CertificationState
from trading_system.paper.rollout import (
    PaperRolloutConfigError,
    RolloutGateState,
    StagedRolloutPlan,
    build_rollout_stage,
    build_rollout_stage_evidence,
    build_staged_rollout_plan,
    evaluate_rollout_stage,
    load_paper_rollout_config,
)
from trading_system.serialization import canonical_hash

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 9, 9, 16, tzinfo=UTC)


def _certification(state: CertificationState = CertificationState.REVIEW_READY) -> (
    CertificationAssessment
):
    return CertificationAssessment(
        "certification-9c", "dossier-9c", NOW - timedelta(hours=1), state,
        ("OPERATIONS_REVIEWER",), (), "sha256:dossier", "sha256:certification-config",
    )


def _plan() -> StagedRolloutPlan:
    config = load_paper_rollout_config(ROOT / "config/paper.phase9d.v1.yaml")
    stages = (
        build_rollout_stage(
            stage_id="OBSERVE", sequence=1, capital_ceiling=Decimal("1000"),
            position_ceiling=1, minimum_observations=10,
            rollback_trigger_codes=("RECONCILIATION_FAILURE", "LIMIT_BREACH"),
        ),
        build_rollout_stage(
            stage_id="LIMITED", sequence=2, capital_ceiling=Decimal("2000"),
            position_ceiling=2, minimum_observations=20,
            rollback_trigger_codes=("LIMIT_BREACH",),
        ),
    )
    return build_staged_rollout_plan(
        config, certification=_certification(), session_id="paper-9d",
        declared_at=NOW, stages=tuple(reversed(stages)),
    )


def test_plan_normalizes_stages_and_grants_no_authority() -> None:
    plan = _plan()
    assert [stage.stage_id for stage in plan.stages] == ["OBSERVE", "LIMITED"]
    assert not plan.stage_activation_authorized
    assert not plan.broker_write_authorized
    assert not plan.live_trading_authorized
    assert canonical_hash(plan) == canonical_hash(plan)


def test_stage_assessments_are_ready_incomplete_or_blocked_without_action() -> None:
    plan = _plan()
    ready_evidence = build_rollout_stage_evidence(
        plan, stage_id="OBSERVE", observed_at=NOW + timedelta(hours=1),
        completed_observations=10, unresolved_incidents=0,
        breached_trigger_codes=(), source_hash="sha256:evidence",
    )
    ready = evaluate_rollout_stage(
        plan, ready_evidence, evaluated_at=NOW + timedelta(hours=2)
    )
    assert ready.state is RolloutGateState.READY_FOR_HUMAN_REVIEW
    assert not ready.stage_activated
    assert not ready.automatic_advancement_performed
    assert not ready.broker_write_performed

    incomplete = evaluate_rollout_stage(
        plan,
        replace(ready_evidence, completed_observations=9),
        evaluated_at=NOW + timedelta(hours=2),
    )
    assert incomplete.state is RolloutGateState.INCOMPLETE
    blocked = evaluate_rollout_stage(
        plan,
        replace(
            ready_evidence, unresolved_incidents=1,
            breached_trigger_codes=("LIMIT_BREACH",),
        ),
        evaluated_at=NOW + timedelta(hours=2),
    )
    assert blocked.state is RolloutGateState.BLOCKED


def test_plan_rejects_ineligible_certification_and_decreasing_limits() -> None:
    config = load_paper_rollout_config(ROOT / "config/paper.phase9d.v1.yaml")
    first = build_rollout_stage(
        stage_id="FIRST", sequence=1, capital_ceiling=Decimal("1000"),
        position_ceiling=2, minimum_observations=1, rollback_trigger_codes=("HALT",),
    )
    second = build_rollout_stage(
        stage_id="SECOND", sequence=2, capital_ceiling=Decimal("999"),
        position_ceiling=2, minimum_observations=1, rollback_trigger_codes=("HALT",),
    )
    with pytest.raises(ValueError, match="review-ready"):
        build_staged_rollout_plan(
            config, certification=_certification(CertificationState.INCOMPLETE),
            session_id="paper-9d", declared_at=NOW, stages=(first,),
        )
    with pytest.raises(ValueError, match="staged-rollout plan"):
        build_staged_rollout_plan(
            config, certification=_certification(), session_id="paper-9d",
            declared_at=NOW, stages=(first, second),
        )


def test_evaluation_rejects_future_evidence_and_undeclared_trigger() -> None:
    plan = _plan()
    future = build_rollout_stage_evidence(
        plan, stage_id="OBSERVE", observed_at=NOW + timedelta(days=2),
        completed_observations=10, unresolved_incidents=0,
        breached_trigger_codes=(), source_hash="sha256:evidence",
    )
    with pytest.raises(ValueError, match="causal"):
        evaluate_rollout_stage(plan, future, evaluated_at=NOW + timedelta(days=1))
    unknown = build_rollout_stage_evidence(
        plan, stage_id="OBSERVE", observed_at=NOW + timedelta(hours=1),
        completed_observations=10, unresolved_incidents=0,
        breached_trigger_codes=("UNDECLARED",), source_hash="sha256:evidence",
    )
    with pytest.raises(ValueError, match="undeclared"):
        evaluate_rollout_stage(plan, unknown, evaluated_at=NOW + timedelta(hours=2))


def test_config_rejects_rollout_authority(tmp_path: Path) -> None:
    source = ROOT / "config/paper.phase9d.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["stage_activation_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PaperRolloutConfigError, match="authority"):
        load_paper_rollout_config(unsafe)
