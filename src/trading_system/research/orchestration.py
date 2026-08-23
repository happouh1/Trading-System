"""Deterministic Phase 2B experiment lifecycle and assignments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType

from trading_system.research.contracts import ResearchRow, WalkForwardFold
from trading_system.serialization import canonical_hash, deterministic_id


class ExperimentStage(StrEnum):
    DEFINED = "DEFINED"
    TRAIN_EVALUATED = "TRAIN_EVALUATED"
    VALIDATION_EVALUATED = "VALIDATION_EVALUATED"
    FROZEN = "FROZEN"
    TEST_EVALUATED = "TEST_EVALUATED"
    COMPLETE = "COMPLETE"


class DatasetPartition(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    EXCLUDED = "EXCLUDED"


_NEXT = {
    ExperimentStage.DEFINED: ExperimentStage.TRAIN_EVALUATED,
    ExperimentStage.TRAIN_EVALUATED: ExperimentStage.VALIDATION_EVALUATED,
    ExperimentStage.VALIDATION_EVALUATED: ExperimentStage.FROZEN,
    ExperimentStage.FROZEN: ExperimentStage.TEST_EVALUATED,
    ExperimentStage.TEST_EVALUATED: ExperimentStage.COMPLETE,
}


@dataclass(frozen=True, slots=True)
class CohortSpec:
    cohort_id: str
    experiment_id: str
    name: str
    filters: Mapping[str, str] = field(default_factory=dict)
    minimum_sample: int = 30

    def __post_init__(self) -> None:
        if not self.name or self.minimum_sample <= 0:
            raise ValueError("cohort name and positive sample threshold are required")
        object.__setattr__(self, "filters", MappingProxyType(dict(self.filters)))
        allowed = {
            "pattern",
            "direction",
            "timeframe",
            "regime",
            "confidence_bucket",
            "decision_action",
            "data_quality_status",
        }
        if not set(self.filters) <= allowed:
            raise ValueError("cohort contains an unsupported filter")

    @property
    def specification_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True, slots=True)
class FoldAssignment:
    assignment_id: str
    experiment_id: str
    fold_id: str
    row_id: str
    partition: DatasetPartition
    reason: str


@dataclass(frozen=True, slots=True)
class ExperimentTransition:
    transition_id: str
    experiment_id: str
    prior_stage: ExperimentStage
    new_stage: ExperimentStage
    occurred_at: datetime
    frozen_definition_hash: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("transition time must be timezone-aware")
        if _NEXT.get(self.prior_stage) is not self.new_stage:
            raise ValueError("invalid experiment lifecycle transition")
        if self.new_stage is ExperimentStage.FROZEN and not self.frozen_definition_hash:
            raise ValueError("freeze requires a definition hash")
        if self.frozen_definition_hash is not None and not self.frozen_definition_hash.startswith(
            "sha256:"
        ):
            raise ValueError("frozen definition hash must use sha256")


def assign_fold_rows(
    experiment_id: str, fold: WalkForwardFold, rows: tuple[ResearchRow, ...]
) -> tuple[FoldAssignment, ...]:
    result: list[FoldAssignment] = []
    for row in sorted(rows, key=lambda item: (item.session_date, item.row_id)):
        partition = DatasetPartition.EXCLUDED
        reason = "OUTSIDE_FOLD"
        if fold.train_start <= row.session_date <= fold.train_end:
            partition, reason = DatasetPartition.TRAIN, "ELIGIBLE"
        elif fold.validation_start <= row.session_date <= fold.validation_end:
            partition, reason = DatasetPartition.VALIDATION, "ELIGIBLE"
        elif fold.test_start <= row.session_date <= fold.test_end:
            partition, reason = DatasetPartition.TEST, "ELIGIBLE"
        cutoff = {
            DatasetPartition.TRAIN: fold.train_end,
            DatasetPartition.VALIDATION: fold.validation_end,
            DatasetPartition.TEST: fold.test_end,
        }.get(partition)
        if cutoff is not None and (
            row.label_available_at is None or row.label_available_at.date() > cutoff
        ):
            partition, reason = DatasetPartition.EXCLUDED, "LABEL_UNAVAILABLE_AT_CUTOFF"
        identity = (experiment_id, fold.fold_id, row.row_id, partition, reason)
        result.append(
            FoldAssignment(
                deterministic_id("fold_assignment", identity),
                experiment_id,
                fold.fold_id,
                row.row_id,
                partition,
                reason,
            )
        )
    return tuple(result)


def symbol_holdout_bucket(symbol: str, buckets: int = 5) -> int:
    if buckets <= 1:
        raise ValueError("at least two symbol buckets are required")
    digest = canonical_hash({"symbol": symbol.upper()})[7:23]
    return int(digest, 16) % buckets


def transition(
    experiment_id: str,
    prior: ExperimentStage,
    new: ExperimentStage,
    *,
    frozen_definition_hash: str | None = None,
    occurred_at: datetime | None = None,
) -> ExperimentTransition:
    timestamp = occurred_at or datetime.now(UTC)
    identity = (experiment_id, prior, new, timestamp, frozen_definition_hash)
    return ExperimentTransition(
        deterministic_id("experiment_transition", identity),
        experiment_id,
        prior,
        new,
        timestamp,
        frozen_definition_hash,
    )
