"""Phase 9D offline staged-rollout review boundary without activation authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.paper.certification import CertificationAssessment, CertificationState
from trading_system.serialization import canonical_hash, deterministic_id


class PaperRolloutConfigError(ValueError):
    pass


class RolloutGateState(StrEnum):
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PaperRolloutConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RolloutStage:
    stage_id: str
    sequence: int
    capital_ceiling: Decimal
    position_ceiling: int
    minimum_observations: int
    rollback_trigger_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.stage_id
            or self.sequence < 1
            or self.capital_ceiling <= 0
            or self.position_ceiling < 1
            or self.minimum_observations < 1
            or not self.rollback_trigger_codes
            or self.rollback_trigger_codes != tuple(sorted(set(self.rollback_trigger_codes)))
            or any(not code for code in self.rollback_trigger_codes)
        ):
            raise ValueError("invalid Phase 9D rollout stage")


@dataclass(frozen=True, slots=True)
class StagedRolloutPlan:
    plan_id: str
    session_id: str
    certification_assessment_id: str
    certification_assessment_hash: str
    declared_at: datetime
    stages: tuple[RolloutStage, ...]
    plan_hash: str
    config_hash: str
    rollout_version: str = "9D.1.0"
    stage_activation_authorized: bool = False
    broker_write_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.plan_id, self.session_id, self.certification_assessment_id))
            or not self.certification_assessment_hash.startswith("sha256:")
            or self.declared_at.tzinfo is None
            or self.declared_at.utcoffset() != UTC.utcoffset(self.declared_at)
            or not self.stages
            or tuple(stage.sequence for stage in self.stages) != tuple(
                range(1, len(self.stages) + 1)
            )
            or any(
                current.capital_ceiling < previous.capital_ceiling
                or current.position_ceiling < previous.position_ceiling
                for previous, current in zip(self.stages, self.stages[1:], strict=False)
            )
            or not self.plan_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.rollout_version != "9D.1.0"
            or self.stage_activation_authorized
            or self.broker_write_authorized
            or self.live_trading_authorized
        ):
            raise ValueError("invalid Phase 9D staged-rollout plan")


@dataclass(frozen=True, slots=True)
class RolloutStageEvidence:
    evidence_id: str
    plan_id: str
    stage_id: str
    observed_at: datetime
    completed_observations: int
    unresolved_incidents: int
    breached_trigger_codes: tuple[str, ...]
    source_hash: str

    def __post_init__(self) -> None:
        if (
            not all((self.evidence_id, self.plan_id, self.stage_id))
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() != UTC.utcoffset(self.observed_at)
            or self.completed_observations < 0
            or self.unresolved_incidents < 0
            or self.breached_trigger_codes != tuple(sorted(set(self.breached_trigger_codes)))
            or not self.source_hash.startswith("sha256:")
        ):
            raise ValueError("invalid Phase 9D rollout evidence")


@dataclass(frozen=True, slots=True)
class RolloutGateAssessment:
    assessment_id: str
    plan_id: str
    stage_id: str
    evaluated_at: datetime
    state: RolloutGateState
    reason_codes: tuple[str, ...]
    evidence_hash: str
    plan_hash: str
    config_hash: str
    rollout_version: str = "9D.1.0"
    stage_activated: bool = False
    automatic_advancement_performed: bool = False
    automatic_rollback_performed: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.plan_id, self.stage_id))
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() != UTC.utcoffset(self.evaluated_at)
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not self.evidence_hash.startswith("sha256:")
            or not self.plan_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.rollout_version != "9D.1.0"
            or self.stage_activated
            or self.automatic_advancement_performed
            or self.automatic_rollback_performed
            or self.broker_write_performed
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9D rollout assessment")


def load_paper_rollout_config(path: str | Path) -> PaperRolloutConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "rollout_version", "mode", "policy", "authority"
    }:
        raise PaperRolloutConfigError("Phase 9D configuration keys are invalid")
    if raw["rollout_version"] != "9D.1.0" or raw["mode"] != (
        "OFFLINE_STAGED_ROLLOUT_REVIEW"
    ):
        raise PaperRolloutConfigError("Phase 9D mode is invalid")
    if raw["policy"] != {
        "require_phase9c_review_ready": True,
        "stage_limits_operator_supplied": True,
        "rollback_triggers_operator_supplied": True,
        "strictly_increasing_stage_sequence": True,
        "nondecreasing_exposure_ceilings": True,
        "assessments_per_stage": 1,
    }:
        raise PaperRolloutConfigError("Phase 9D policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or any(value is not False for value in authority.values()):
        raise PaperRolloutConfigError("Phase 9D authority must remain disabled")
    if set(authority) != {
        "default_stage_limits_enabled", "stage_activation_enabled",
        "automatic_advancement_enabled", "automatic_rollback_enabled",
        "deployment_enabled", "network_enabled", "broker_writes_enabled",
        "live_trading_enabled",
    }:
        raise PaperRolloutConfigError("Phase 9D authority keys are invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return PaperRolloutConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_rollout_stage(
    *, stage_id: str, sequence: int, capital_ceiling: Decimal,
    position_ceiling: int, minimum_observations: int,
    rollback_trigger_codes: tuple[str, ...],
) -> RolloutStage:
    return RolloutStage(
        stage_id, sequence, capital_ceiling, position_ceiling, minimum_observations,
        tuple(sorted(rollback_trigger_codes)),
    )


def build_staged_rollout_plan(
    config: PaperRolloutConfig,
    *,
    certification: CertificationAssessment,
    session_id: str,
    declared_at: datetime,
    stages: tuple[RolloutStage, ...],
) -> StagedRolloutPlan:
    if certification.state is not CertificationState.REVIEW_READY:
        raise ValueError("Phase 9D requires Phase 9C review-ready evidence")
    normalized = tuple(sorted(stages, key=lambda stage: stage.sequence))
    content = (
        session_id, certification.assessment_id, canonical_hash(certification), declared_at,
        normalized, config.config_hash,
    )
    return StagedRolloutPlan(
        deterministic_id("paper_staged_rollout_plan", content), session_id,
        certification.assessment_id, canonical_hash(certification), declared_at, normalized,
        canonical_hash(content), config.config_hash,
    )


def build_rollout_stage_evidence(
    plan: StagedRolloutPlan,
    *,
    stage_id: str,
    observed_at: datetime,
    completed_observations: int,
    unresolved_incidents: int,
    breached_trigger_codes: tuple[str, ...],
    source_hash: str,
) -> RolloutStageEvidence:
    if stage_id not in {stage.stage_id for stage in plan.stages}:
        raise ValueError("Phase 9D stage is not in the rollout plan")
    normalized = tuple(sorted(breached_trigger_codes))
    content = (
        plan.plan_id, stage_id, observed_at, completed_observations,
        unresolved_incidents, normalized, source_hash,
    )
    return RolloutStageEvidence(
        deterministic_id("paper_rollout_stage_evidence", content), plan.plan_id, stage_id,
        observed_at, completed_observations, unresolved_incidents, normalized, source_hash,
    )


def evaluate_rollout_stage(
    plan: StagedRolloutPlan,
    evidence: RolloutStageEvidence,
    *,
    evaluated_at: datetime,
) -> RolloutGateAssessment:
    if evidence.plan_id != plan.plan_id:
        raise ValueError("Phase 9D evidence belongs to another plan")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise ValueError("Phase 9D evaluation time must be UTC")
    if evidence.observed_at < plan.declared_at or evidence.observed_at > evaluated_at:
        raise ValueError("Phase 9D evidence time is outside the causal evaluation window")
    stage = next((item for item in plan.stages if item.stage_id == evidence.stage_id), None)
    if stage is None:
        raise ValueError("Phase 9D evidence stage is not in the rollout plan")
    unknown_breaches = set(evidence.breached_trigger_codes) - set(stage.rollback_trigger_codes)
    if unknown_breaches:
        raise ValueError("Phase 9D evidence contains undeclared rollback triggers")
    reasons: set[str] = set()
    if evidence.completed_observations < stage.minimum_observations:
        reasons.add("MINIMUM_OBSERVATIONS_NOT_MET")
    if evidence.unresolved_incidents:
        reasons.add("UNRESOLVED_INCIDENTS")
    if evidence.breached_trigger_codes:
        reasons.add("ROLLBACK_TRIGGER_BREACHED")
    if evidence.unresolved_incidents or evidence.breached_trigger_codes:
        state = RolloutGateState.BLOCKED
    elif reasons:
        state = RolloutGateState.INCOMPLETE
    else:
        state = RolloutGateState.READY_FOR_HUMAN_REVIEW
    reason_codes = tuple(sorted(reasons))
    identity = (
        plan.plan_id, stage.stage_id, evaluated_at, state, reason_codes,
        canonical_hash(evidence), plan.plan_hash,
    )
    return RolloutGateAssessment(
        deterministic_id("paper_rollout_gate_assessment", identity), plan.plan_id,
        stage.stage_id, evaluated_at, state, reason_codes, canonical_hash(evidence),
        plan.plan_hash, plan.config_hash,
    )
