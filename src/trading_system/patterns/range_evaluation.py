"""Evidence-gated descriptive evaluation for Phase 7F range outcomes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.domain import Direction, Timeframe
from trading_system.patterns.range_experiment import (
    RangeExperimentAssignment,
    RangeExperimentMaterialization,
)
from trading_system.patterns.range_outcome import RangeEntryOutcome
from trading_system.research import WalkForwardFold
from trading_system.research.orchestration import DatasetPartition
from trading_system.research.statistics import DescriptiveStatistics, summarize_returns
from trading_system.serialization import canonical_hash, deterministic_id


class RangeEvaluationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeEvaluationConfig:
    values: Mapping[str, object]
    config_hash: str


def load_range_evaluation_config(path: str | Path) -> RangeEvaluationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"evaluation_version", "metrics", "authority"}:
        raise RangeEvaluationConfigError("range evaluation top-level keys are invalid")
    if raw["evaluation_version"] != "7G.1.0":
        raise RangeEvaluationConfigError("evaluation_version must be 7G.1.0")
    if raw["metrics"] != {
        "primary_value": "NET_DIRECTIONAL_RETURN",
        "retain_all_horizons": True,
        "cluster_key": "BOX_ID",
        "require_phase7c_observation_gate": True,
        "require_phase7c_cluster_gate": True,
        "bootstrap_confidence_interval": "95_PERCENTILE",
    }:
        raise RangeEvaluationConfigError("Phase 7G metric policy is invalid")
    if raw["authority"] != {
        "descriptive_statistics_only": True,
        "hypothesis_tests_enabled": False,
        "efficacy_claims_enabled": False,
        "parameter_selection_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeEvaluationConfigError("Phase 7G authority must remain descriptive-only")
    metrics = raw["metrics"]
    authority = raw["authority"]
    assert isinstance(metrics, dict) and isinstance(authority, dict)
    return RangeEvaluationConfig(
        MappingProxyType(
            {
                "evaluation_version": raw["evaluation_version"],
                "metrics": MappingProxyType(dict(metrics)),
                "authority": MappingProxyType(dict(authority)),
            }
        ),
        canonical_hash(raw),
    )


@dataclass(frozen=True, slots=True)
class RangeEvaluationAssignment:
    assignment_id: str
    plan_id: str
    fold_id: str
    phase7c_assignment_id: str
    outcome_id: str
    entry_id: str
    box_id: str
    symbol: str
    timeframe: Timeframe
    direction: Direction
    horizon_bars: int
    cluster_id: str
    partition: DatasetPartition
    reason: str

    def __post_init__(self) -> None:
        required = (
            self.assignment_id,
            self.plan_id,
            self.fold_id,
            self.phase7c_assignment_id,
            self.outcome_id,
            self.entry_id,
            self.box_id,
            self.symbol,
            self.cluster_id,
            self.reason,
        )
        if not all(required) or self.horizon_bars <= 0:
            raise ValueError("complete range evaluation assignment is required")


@dataclass(frozen=True, slots=True)
class RangeDescriptiveStatistics:
    count: int
    win_rate: Decimal | None
    mean_net_directional_return: Decimal | None
    median_net_directional_return: Decimal | None
    profit_factor: Decimal | None
    maximum_drawdown_return: Decimal
    p10_net_directional_return: Decimal | None
    p90_net_directional_return: Decimal | None
    p10_mfe_box_units: Decimal | None
    p90_mfe_box_units: Decimal | None
    p10_mae_box_units: Decimal | None
    p90_mae_box_units: Decimal | None
    mean_ci_low: Decimal | None
    mean_ci_high: Decimal | None


@dataclass(frozen=True, slots=True)
class RangeCohortSummary:
    summary_id: str
    plan_id: str
    fold_id: str
    partition: DatasetPartition
    timeframe: Timeframe
    direction: Direction
    horizon_bars: int
    observation_count: int
    independent_cluster_count: int
    gate_passed: bool
    statistics: RangeDescriptiveStatistics | None
    config_hash: str
    evaluation_version: str = "7G.1.0"

    def __post_init__(self) -> None:
        if not self.summary_id or not self.plan_id or not self.fold_id:
            raise ValueError("complete cohort summary identity is required")
        if self.partition is DatasetPartition.EXCLUDED:
            raise ValueError("excluded assignments cannot form a cohort summary")
        if self.observation_count < 0 or self.independent_cluster_count < 0:
            raise ValueError("cohort counts cannot be negative")
        if self.independent_cluster_count > self.observation_count:
            raise ValueError("cluster count cannot exceed observation count")
        if self.gate_passed != (self.statistics is not None):
            raise ValueError("statistics exist if and only if the evidence gate passes")
        if self.evaluation_version != "7G.1.0":
            raise ValueError("evaluation_version is fixed for Phase 7G")


@dataclass(frozen=True, slots=True)
class RangeEvaluationResult:
    assignments: tuple[RangeEvaluationAssignment, ...]
    summaries: tuple[RangeCohortSummary, ...]


def evaluate_range_outcomes(
    config: RangeEvaluationConfig,
    *,
    experiment: RangeExperimentMaterialization,
    outcomes: tuple[RangeEntryOutcome, ...],
) -> RangeEvaluationResult:
    if len({item.outcome_id for item in outcomes}) != len(outcomes):
        raise ValueError("outcome identities must be unique")
    fold_by_id = {item.fold_id: item for item in experiment.folds}
    base_by_key: dict[tuple[str, str, int], RangeExperimentAssignment] = {}
    for base_assignment in experiment.assignments:
        base_key = (
            base_assignment.fold_id,
            base_assignment.box_id,
            base_assignment.horizon_bars,
        )
        if base_key in base_by_key:
            raise ValueError("Phase 7C assignments are ambiguous for box horizon")
        base_by_key[base_key] = base_assignment
    assignments: list[RangeEvaluationAssignment] = []
    outcome_by_id = {item.outcome_id: item for item in outcomes}
    for outcome in sorted(outcomes, key=lambda item: (item.label_available_at, item.outcome_id)):
        matching = [
            base_assignment
            for base_key, base_assignment in base_by_key.items()
            if base_key[1:] == (outcome.box_id, outcome.horizon_bars)
        ]
        if experiment.folds and not matching:
            raise ValueError("Phase 7F outcome has no Phase 7C assignment")
        for base in matching:
            if outcome.symbol != base.symbol or outcome.timeframe is not base.timeframe:
                raise ValueError("Phase 7F outcome disagrees with its Phase 7C assignment")
            partition = base.partition
            reason = base.reason
            cutoff = _cutoff(fold_by_id[base.fold_id], partition)
            if cutoff is not None and outcome.label_available_at.date() > cutoff:
                partition = DatasetPartition.EXCLUDED
                reason = "PHASE7F_LABEL_UNAVAILABLE_AT_CUTOFF"
            assignment_identity = (
                base.assignment_id,
                outcome.outcome_id,
                partition,
                reason,
                "7G.1.0",
            )
            assignments.append(
                RangeEvaluationAssignment(
                    deterministic_id("range_evaluation_assignment", assignment_identity),
                    experiment.plan.plan_id,
                    base.fold_id,
                    base.assignment_id,
                    outcome.outcome_id,
                    outcome.entry_id,
                    outcome.box_id,
                    outcome.symbol,
                    outcome.timeframe,
                    outcome.direction,
                    outcome.horizon_bars,
                    outcome.box_id,
                    partition,
                    reason,
                )
            )
    groups: dict[
        tuple[str, DatasetPartition, Timeframe, Direction, int],
        list[RangeEvaluationAssignment],
    ] = {}
    for evaluation_assignment in assignments:
        if evaluation_assignment.partition is DatasetPartition.EXCLUDED:
            continue
        groups.setdefault(
            (
                evaluation_assignment.fold_id,
                evaluation_assignment.partition,
                evaluation_assignment.timeframe,
                evaluation_assignment.direction,
                evaluation_assignment.horizon_bars,
            ),
            [],
        ).append(evaluation_assignment)
    summaries: list[RangeCohortSummary] = []
    plan = experiment.plan
    for cohort_key, group in sorted(
        groups.items(), key=lambda pair: tuple(str(value) for value in pair[0])
    ):
        fold_id, partition, timeframe, direction, horizon = cohort_key
        clusters = len({item.cluster_id for item in group})
        passed = len(group) >= plan.minimum_observations and clusters >= plan.minimum_clusters
        stats = None
        if passed:
            selected = tuple(outcome_by_id[item.outcome_id] for item in group)
            raw_stats = summarize_returns(
                tuple(item.net_directional_return for item in selected),
                seed=plan.seed,
                bootstrap_samples=plan.bootstrap_samples,
                mfe_values=tuple(item.maximum_favorable_box_units for item in selected),
                mae_values=tuple(item.maximum_adverse_box_units for item in selected),
            )
            stats = _range_statistics(raw_stats)
        cohort_identity = (
            plan.plan_id,
            cohort_key,
            len(group),
            clusters,
            config.config_hash,
        )
        summaries.append(
            RangeCohortSummary(
                deterministic_id("range_cohort_summary", cohort_identity),
                plan.plan_id,
                fold_id,
                partition,
                timeframe,
                direction,
                horizon,
                len(group),
                clusters,
                passed,
                stats,
                config.config_hash,
            )
        )
    return RangeEvaluationResult(
        tuple(sorted(assignments, key=lambda item: (item.fold_id, item.outcome_id))),
        tuple(summaries),
    )


def _cutoff(fold: WalkForwardFold, partition: DatasetPartition) -> date | None:
    return {
        DatasetPartition.TRAIN: fold.train_end,
        DatasetPartition.VALIDATION: fold.validation_end,
        DatasetPartition.TEST: fold.test_end,
    }.get(partition)


def _range_statistics(value: DescriptiveStatistics) -> RangeDescriptiveStatistics:
    return RangeDescriptiveStatistics(
        value.count,
        value.win_rate,
        value.mean_net_r,
        value.median_net_r,
        value.profit_factor,
        value.maximum_drawdown_r,
        value.p10_net_r,
        value.p90_net_r,
        value.p10_mfe_r,
        value.p90_mfe_r,
        value.p10_mae_r,
        value.p90_mae_r,
        value.mean_ci_low,
        value.mean_ci_high,
    )
