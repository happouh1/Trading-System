"""Causal Phase 4D walk-forward evaluation for supplied Phase 4C cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal
from enum import StrEnum

from trading_system.options.experiment_config import OptionsExperimentConfig
from trading_system.options.validation import (
    OptionBacktestMetrics,
    OptionsValidationEngine,
    OptionValidationCase,
    OptionValidationResult,
    OptionValidationStatus,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class OptionExperimentStage(StrEnum):
    DEFINED = "DEFINED"
    DEVELOPMENT_EVALUATED = "DEVELOPMENT_EVALUATED"
    FROZEN = "FROZEN"
    TEST_EVALUATED = "TEST_EVALUATED"
    COMPLETE = "COMPLETE"


class OptionExperimentPartition(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    EXCLUDED = "EXCLUDED"


@dataclass(frozen=True, slots=True)
class OptionExperimentDefinition:
    experiment_id: str
    source_revision: str
    session_dates: tuple[date, ...]
    case_ids: tuple[str, ...]
    phase4c_config_hash: str
    phase4d_config_hash: str

    def __post_init__(self) -> None:
        if not self.source_revision or not self.case_ids:
            raise ValueError("experiment source revision and cases are required")
        if tuple(sorted(set(self.session_dates))) != self.session_dates:
            raise ValueError("experiment sessions must be unique and strictly increasing")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("experiment case IDs must be unique")

    @classmethod
    def create(
        cls,
        *,
        source_revision: str,
        session_dates: tuple[date, ...],
        cases: tuple[OptionValidationCase, ...],
        phase4c_config_hash: str,
        phase4d_config_hash: str,
    ) -> OptionExperimentDefinition:
        ordered_cases = tuple(
            sorted(cases, key=lambda item: (item.screen_known_at, item.case_id))
        )
        case_ids = tuple(item.case_id for item in ordered_cases)
        identity = (
            source_revision,
            session_dates,
            case_ids,
            phase4c_config_hash,
            phase4d_config_hash,
        )
        return cls(
            deterministic_id("option_experiment", identity),
            source_revision,
            session_dates,
            case_ids,
            phase4c_config_hash,
            phase4d_config_hash,
        )

    @property
    def definition_hash(self) -> str:
        return canonical_hash(self)

    def to_json(self) -> str:
        return canonical_json(self)


@dataclass(frozen=True, slots=True)
class OptionExperimentFold:
    fold_id: str
    experiment_id: str
    ordinal: int
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date

    def __post_init__(self) -> None:
        boundaries = (
            self.train_start,
            self.train_end,
            self.validation_start,
            self.validation_end,
            self.test_start,
            self.test_end,
        )
        if not self.fold_id or not self.experiment_id or self.ordinal < 0:
            raise ValueError("fold identity and nonnegative ordinal are required")
        if tuple(sorted(boundaries)) != boundaries:
            raise ValueError("fold boundaries must be chronological")


@dataclass(frozen=True, slots=True)
class OptionExperimentAssignment:
    assignment_id: str
    experiment_id: str
    fold_id: str
    case_id: str
    partition: OptionExperimentPartition
    reason: str

    def __post_init__(self) -> None:
        if not all(
            (self.assignment_id, self.experiment_id, self.fold_id, self.case_id, self.reason)
        ):
            raise ValueError("assignment identity and reason are required")


@dataclass(frozen=True, slots=True)
class OptionFoldEvaluation:
    evaluation_id: str
    experiment_id: str
    fold_id: str
    partition: OptionExperimentPartition
    cutoff: date
    result_ids: tuple[str, ...]
    metrics: OptionBacktestMetrics
    sample_sufficient: bool
    disclosures: tuple[str, ...]
    phase4c_config_hash: str
    phase4d_config_hash: str

    def __post_init__(self) -> None:
        if self.partition is OptionExperimentPartition.EXCLUDED:
            raise ValueError("excluded is not an evaluable partition")
        if len(set(self.result_ids)) != len(self.result_ids):
            raise ValueError("fold evaluation result IDs must be unique")
        if not self.phase4c_config_hash or not self.phase4d_config_hash:
            raise ValueError("fold evaluation configuration identity is required")

    def to_json(self) -> str:
        return canonical_json(self)


@dataclass(frozen=True, slots=True)
class OptionExperimentTransition:
    transition_id: str
    experiment_id: str
    prior_stage: OptionExperimentStage
    new_stage: OptionExperimentStage
    frozen_definition_hash: str | None

    def __post_init__(self) -> None:
        if self.frozen_definition_hash is not None and not self.frozen_definition_hash.startswith(
            "sha256:"
        ):
            raise ValueError("frozen definition hash must use sha256")

    @classmethod
    def create(
        cls,
        experiment_id: str,
        prior_stage: OptionExperimentStage,
        new_stage: OptionExperimentStage,
        frozen_definition_hash: str | None = None,
    ) -> OptionExperimentTransition:
        allowed = {
            OptionExperimentStage.DEFINED: OptionExperimentStage.DEVELOPMENT_EVALUATED,
            OptionExperimentStage.DEVELOPMENT_EVALUATED: OptionExperimentStage.FROZEN,
            OptionExperimentStage.FROZEN: OptionExperimentStage.TEST_EVALUATED,
            OptionExperimentStage.TEST_EVALUATED: OptionExperimentStage.COMPLETE,
        }
        if allowed.get(prior_stage) is not new_stage:
            raise ValueError("invalid options experiment transition")
        if new_stage is OptionExperimentStage.FROZEN and frozen_definition_hash is None:
            raise ValueError("freeze transition requires a definition hash")
        identity = (experiment_id, prior_stage, new_stage, frozen_definition_hash)
        return cls(
            deterministic_id("option_experiment_transition", identity),
            experiment_id,
            prior_stage,
            new_stage,
            frozen_definition_hash,
        )


class OptionsExperimentEngine:
    def __init__(
        self,
        config: OptionsExperimentConfig,
        validation_engine: OptionsValidationEngine,
    ) -> None:
        self.config = config
        self.validation_engine = validation_engine

    def define(
        self,
        *,
        source_revision: str,
        sessions: tuple[date, ...],
        cases: tuple[OptionValidationCase, ...],
    ) -> OptionExperimentDefinition:
        definition = OptionExperimentDefinition.create(
            source_revision=source_revision,
            session_dates=sessions,
            cases=cases,
            phase4c_config_hash=self.validation_engine.config.config_hash,
            phase4d_config_hash=self.config.config_hash,
        )
        if not self.folds(definition):
            raise ValueError("session history is insufficient for one complete walk-forward fold")
        return definition

    def folds(self, definition: OptionExperimentDefinition) -> tuple[OptionExperimentFold, ...]:
        sessions = definition.session_dates
        train = self.config.integer("folds", "minimum_train_sessions")
        validation = self.config.integer("folds", "validation_sessions")
        test = self.config.integer("folds", "test_sessions")
        step = self.config.integer("folds", "step_sessions")
        embargo = self.config.integer("folds", "embargo_sessions")
        train_end = train - 1
        folds: list[OptionExperimentFold] = []
        while True:
            validation_start = train_end + embargo + 1
            validation_end = validation_start + validation - 1
            test_start = validation_end + embargo + 1
            test_end = test_start + test - 1
            if test_end >= len(sessions):
                break
            ordinal = len(folds)
            identity = (
                definition.experiment_id,
                ordinal,
                sessions[0],
                sessions[train_end],
                sessions[validation_start],
                sessions[validation_end],
                sessions[test_start],
                sessions[test_end],
            )
            folds.append(
                OptionExperimentFold(
                    deterministic_id("option_experiment_fold", identity),
                    definition.experiment_id,
                    ordinal,
                    sessions[0],
                    sessions[train_end],
                    sessions[validation_start],
                    sessions[validation_end],
                    sessions[test_start],
                    sessions[test_end],
                )
            )
            train_end += step
            if train_end >= len(sessions):
                break
        return tuple(folds)

    def assignments(
        self,
        definition: OptionExperimentDefinition,
        fold: OptionExperimentFold,
        cases: tuple[OptionValidationCase, ...],
    ) -> tuple[OptionExperimentAssignment, ...]:
        declared = set(definition.session_dates)
        assignments: list[OptionExperimentAssignment] = []
        for case in sorted(cases, key=lambda item: (item.screen_known_at, item.case_id)):
            screen_date = case.screen_known_at.astimezone(UTC).date()
            partition = OptionExperimentPartition.EXCLUDED
            reason = "OUTSIDE_FOLD"
            cutoff: date | None = None
            if screen_date not in declared:
                reason = "SCREEN_SESSION_NOT_DECLARED"
            elif fold.train_start <= screen_date <= fold.train_end:
                partition, reason, cutoff = (
                    OptionExperimentPartition.TRAIN,
                    "ELIGIBLE",
                    fold.train_end,
                )
            elif fold.validation_start <= screen_date <= fold.validation_end:
                partition, reason, cutoff = (
                    OptionExperimentPartition.VALIDATION,
                    "ELIGIBLE",
                    fold.validation_end,
                )
            elif fold.test_start <= screen_date <= fold.test_end:
                partition, reason, cutoff = (
                    OptionExperimentPartition.TEST,
                    "ELIGIBLE",
                    fold.test_end,
                )
            if cutoff is not None and case.exit.as_of.astimezone(UTC).date() > cutoff:
                partition, reason = (
                    OptionExperimentPartition.EXCLUDED,
                    "LABEL_UNAVAILABLE_AT_CUTOFF",
                )
            identity = (definition.experiment_id, fold.fold_id, case.case_id, partition, reason)
            assignments.append(
                OptionExperimentAssignment(
                    deterministic_id("option_experiment_assignment", identity),
                    definition.experiment_id,
                    fold.fold_id,
                    case.case_id,
                    partition,
                    reason,
                )
            )
        return tuple(assignments)

    def evaluate_partition(
        self,
        definition: OptionExperimentDefinition,
        fold: OptionExperimentFold,
        partition: OptionExperimentPartition,
        cases: tuple[OptionValidationCase, ...],
    ) -> OptionFoldEvaluation:
        if partition not in {
            OptionExperimentPartition.TRAIN,
            OptionExperimentPartition.VALIDATION,
            OptionExperimentPartition.TEST,
        }:
            raise ValueError("only chronological partitions can be evaluated")
        assignments = self.assignments(definition, fold, cases)
        eligible_ids = {
            item.case_id for item in assignments if item.partition is partition
        }
        eligible_cases = tuple(item for item in cases if item.case_id in eligible_ids)
        results = tuple(self.validation_engine.evaluate(item) for item in eligible_cases)
        ordered_results = tuple(sorted(results, key=lambda item: (item.known_at, item.result_id)))
        metrics = _metrics(ordered_results)
        cutoff = {
            OptionExperimentPartition.TRAIN: fold.train_end,
            OptionExperimentPartition.VALIDATION: fold.validation_end,
            OptionExperimentPartition.TEST: fold.test_end,
        }[partition]
        minimum = self.config.integer("evaluation", "minimum_partition_sample")
        sample_sufficient = metrics.completed_count >= minimum
        disclosures = [
            "CASE_LEVEL_METRICS_ONLY_NO_PORTFOLIO_CAPITAL_ALLOCATION",
            "OVERLAPPING_CASES_MAY_SHARE_TIME_AND_CAPITAL",
            "NO_PARAMETER_OPTIMIZATION_OR_PROMOTION_AUTHORITY",
        ]
        if not sample_sufficient:
            disclosures.append("PARTITION_SAMPLE_BELOW_CONFIGURED_MINIMUM")
        result_ids = tuple(item.result_id for item in ordered_results)
        identity = (
            definition.experiment_id,
            fold.fold_id,
            partition,
            cutoff,
            result_ids,
            self.validation_engine.config.config_hash,
            self.config.config_hash,
        )
        return OptionFoldEvaluation(
            deterministic_id("option_fold_evaluation", identity),
            definition.experiment_id,
            fold.fold_id,
            partition,
            cutoff,
            result_ids,
            metrics,
            sample_sufficient,
            tuple(sorted(disclosures)),
            self.validation_engine.config.config_hash,
            self.config.config_hash,
        )

    @staticmethod
    def frozen_definition_hash(
        definition: OptionExperimentDefinition,
        folds: tuple[OptionExperimentFold, ...],
        development: tuple[OptionFoldEvaluation, ...],
    ) -> str:
        if any(item.partition is OptionExperimentPartition.TEST for item in development):
            raise ValueError("test evaluations cannot enter the pre-test freeze")
        return canonical_hash(
            {
                "definition_hash": definition.definition_hash,
                "fold_ids": tuple(item.fold_id for item in folds),
                "development_evaluation_ids": tuple(
                    item.evaluation_id
                    for item in sorted(development, key=lambda value: value.evaluation_id)
                ),
            }
        )


def _metrics(results: tuple[OptionValidationResult, ...]) -> OptionBacktestMetrics:
    completed = tuple(item for item in results if item.status is OptionValidationStatus.COMPLETED)
    net_values = tuple(item.net_pnl for item in completed if item.net_pnl is not None)
    returns = tuple(item.return_on_debit for item in completed if item.return_on_debit is not None)
    wins = sum(value > 0 for value in net_values)
    losses = sum(value < 0 for value in net_values)
    breakeven = sum(value == 0 for value in net_values)
    equity = Decimal(0)
    peak = Decimal(0)
    maximum_drawdown = Decimal(0)
    for value in net_values:
        equity += value
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, peak - equity)
    ordered_returns = tuple(sorted(returns))
    midpoint = len(ordered_returns) // 2
    median = None
    if ordered_returns:
        median = (
            ordered_returns[midpoint]
            if len(ordered_returns) % 2
            else (ordered_returns[midpoint - 1] + ordered_returns[midpoint]) / 2
        )
    return OptionBacktestMetrics(
        len(completed),
        len(results) - len(completed),
        wins,
        losses,
        breakeven,
        Decimal(wins) / len(completed) if completed else None,
        sum(net_values, Decimal(0)),
        sum(net_values, Decimal(0)) / len(completed) if completed else None,
        sum(returns, Decimal(0)) / len(completed) if completed else None,
        median,
        maximum_drawdown,
    )
