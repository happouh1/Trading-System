"""Preregister and materialize chronological Phase 7C range experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from trading_system.domain import Timeframe
from trading_system.patterns.range_experiment_config import RangeExperimentConfig
from trading_system.patterns.range_reclaim import RangeBox
from trading_system.patterns.range_research import RangeBoxOutcome
from trading_system.research import (
    ResearchRow,
    WalkForwardFold,
    WalkForwardSpec,
    build_walk_forward_folds,
)
from trading_system.research.orchestration import DatasetPartition, assign_fold_rows
from trading_system.serialization import canonical_hash, deterministic_id


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RangeExperimentPlan:
    plan_id: str
    registered_at: datetime
    source_run_ids: tuple[str, ...]
    universe_revision: str
    box_config_hash: str
    label_config_hash: str
    experiment_config_hash: str
    code_version: str
    folds: WalkForwardSpec
    minimum_observations: int
    minimum_clusters: int
    familywise_alpha: Decimal
    bootstrap_samples: int
    seed: int
    definition_hash: str
    experiment_version: str = "7C.1.0"

    def __post_init__(self) -> None:
        _aware(self.registered_at, "registered_at")
        required = (
            self.plan_id, self.universe_revision, self.box_config_hash,
            self.label_config_hash, self.experiment_config_hash, self.code_version,
        )
        if not all(required) or not self.source_run_ids:
            raise ValueError("complete experiment identity and provenance are required")
        if len(set(self.source_run_ids)) != len(self.source_run_ids):
            raise ValueError("source runs must be unique")
        if self.minimum_observations <= 0 or self.minimum_clusters <= 0:
            raise ValueError("evidence gates must be positive")
        if not self.definition_hash.startswith("sha256:"):
            raise ValueError("definition_hash must use sha256")
        if self.experiment_version != "7C.1.0":
            raise ValueError("experiment_version is fixed for Phase 7C")


def preregister_range_experiment(
    config: RangeExperimentConfig,
    *,
    registered_at: datetime,
    source_run_ids: tuple[str, ...],
    universe_revision: str,
    box_config_hash: str,
    label_config_hash: str,
    code_version: str,
) -> RangeExperimentPlan:
    _aware(registered_at, "registered_at")
    definition = {
        "source_run_ids": source_run_ids,
        "universe_revision": universe_revision,
        "box_config_hash": box_config_hash,
        "label_config_hash": label_config_hash,
        "experiment_config_hash": config.config_hash,
        "code_version": code_version,
        "folds": config.folds,
        "minimum_observations": config.minimum_observations,
        "minimum_clusters": config.minimum_clusters,
        "familywise_alpha": config.familywise_alpha,
        "bootstrap_samples": config.bootstrap_samples,
        "seed": config.seed,
        "experiment_version": "7C.1.0",
    }
    definition_hash = canonical_hash(definition)
    plan_id = deterministic_id("range_experiment_plan", (definition_hash, registered_at))
    return RangeExperimentPlan(
        plan_id, registered_at, source_run_ids, universe_revision, box_config_hash,
        label_config_hash, config.config_hash, code_version, config.folds,
        config.minimum_observations, config.minimum_clusters, config.familywise_alpha,
        config.bootstrap_samples, config.seed, definition_hash,
    )


@dataclass(frozen=True, slots=True)
class RangeExperimentAssignment:
    assignment_id: str
    plan_id: str
    fold_id: str
    outcome_id: str
    box_id: str
    symbol: str
    timeframe: Timeframe
    horizon_bars: int
    cluster_id: str
    partition: DatasetPartition
    reason: str
    label_available_at: datetime

    def __post_init__(self) -> None:
        if not all(
            (
                self.assignment_id,
                self.plan_id,
                self.fold_id,
                self.outcome_id,
                self.box_id,
                self.symbol,
                self.cluster_id,
                self.reason,
            )
        ):
            raise ValueError("complete assignment identity is required")
        if self.horizon_bars <= 0:
            raise ValueError("assignment horizon must be positive")
        _aware(self.label_available_at, "label_available_at")


@dataclass(frozen=True, slots=True)
class RangeEvidenceGate:
    gate_id: str
    plan_id: str
    fold_id: str
    partition: DatasetPartition
    timeframe: Timeframe
    horizon_bars: int
    observation_count: int
    independent_cluster_count: int
    passed: bool

    def __post_init__(self) -> None:
        if not self.gate_id or not self.plan_id or not self.fold_id:
            raise ValueError("complete evidence-gate identity is required")
        if self.partition is DatasetPartition.EXCLUDED:
            raise ValueError("excluded rows cannot form an evidence gate")
        if self.horizon_bars <= 0:
            raise ValueError("gate horizon must be positive")
        if self.observation_count < 0 or self.independent_cluster_count < 0:
            raise ValueError("gate counts cannot be negative")
        if self.independent_cluster_count > self.observation_count:
            raise ValueError("cluster count cannot exceed observation count")


@dataclass(frozen=True, slots=True)
class RangeExperimentMaterialization:
    plan: RangeExperimentPlan
    folds: tuple[WalkForwardFold, ...]
    assignments: tuple[RangeExperimentAssignment, ...]
    gates: tuple[RangeEvidenceGate, ...]


def materialize_range_experiment(
    plan: RangeExperimentPlan,
    *,
    boxes: tuple[RangeBox, ...],
    outcomes: tuple[RangeBoxOutcome, ...],
    sessions: tuple[date, ...],
) -> RangeExperimentMaterialization:
    if tuple(sorted(set(sessions))) != sessions:
        raise ValueError("sessions must be unique and strictly increasing")
    box_by_id = {box.box_id: box for box in boxes}
    if len(box_by_id) != len(boxes):
        raise ValueError("box identities must be unique")
    if len({item.outcome_id for item in outcomes}) != len(outcomes):
        raise ValueError("outcome identities must be unique")
    rows: list[ResearchRow] = []
    outcome_by_id: dict[str, RangeBoxOutcome] = {}
    for outcome in outcomes:
        box = box_by_id.get(outcome.box_id)
        if box is None:
            raise ValueError("every outcome must reference a supplied box")
        if outcome.symbol != box.symbol or outcome.timeframe is not box.timeframe:
            raise ValueError("outcome and box series disagree")
        outcome_by_id[outcome.outcome_id] = outcome
        rows.append(
            ResearchRow(
                outcome.outcome_id,
                box.box_id,
                box.symbol,
                box.known_at.date(),
                outcome.label_available_at,
                outcome.terminal_location.value,
                None,
                {"timeframe": box.timeframe.value, "horizon_bars": outcome.horizon_bars},
            )
        )
    folds = build_walk_forward_folds(plan.plan_id, sessions, plan.folds)
    assignments: list[RangeExperimentAssignment] = []
    for fold in folds:
        for fold_assignment in assign_fold_rows(plan.plan_id, fold, tuple(rows)):
            outcome = outcome_by_id[fold_assignment.row_id]
            box = box_by_id[outcome.box_id]
            assignment_identity = (
                fold_assignment.assignment_id,
                box.box_id,
                "BOX_ID",
                "7C.1.0",
            )
            assignments.append(
                RangeExperimentAssignment(
                    deterministic_id("range_experiment_assignment", assignment_identity),
                    plan.plan_id, fold.fold_id, outcome.outcome_id, box.box_id,
                    box.symbol, box.timeframe, outcome.horizon_bars, box.box_id,
                    fold_assignment.partition, fold_assignment.reason,
                    outcome.label_available_at,
                )
            )
    groups: dict[tuple[str, DatasetPartition, Timeframe, int], list[RangeExperimentAssignment]] = {}
    for assignment in assignments:
        if assignment.partition is DatasetPartition.EXCLUDED:
            continue
        groups.setdefault(
            (
                assignment.fold_id,
                assignment.partition,
                assignment.timeframe,
                assignment.horizon_bars,
            ),
            [],
        ).append(assignment)
    gates: list[RangeEvidenceGate] = []
    for key, group in sorted(groups.items(), key=lambda pair: tuple(str(v) for v in pair[0])):
        fold_id, partition, timeframe, horizon = key
        clusters = len({item.cluster_id for item in group})
        passed = len(group) >= plan.minimum_observations and clusters >= plan.minimum_clusters
        gate_identity = (
            plan.plan_id, fold_id, partition, timeframe, horizon, len(group), clusters
        )
        gates.append(
            RangeEvidenceGate(
                deterministic_id("range_evidence_gate", gate_identity), plan.plan_id, fold_id,
                partition, timeframe, horizon, len(group), clusters, passed,
            )
        )
    return RangeExperimentMaterialization(
        plan,
        folds,
        tuple(sorted(assignments, key=lambda item: (item.fold_id, item.outcome_id))),
        tuple(gates),
    )
