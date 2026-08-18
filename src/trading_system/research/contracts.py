"""Immutable Phase 2A empirical-research contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class ExperimentStatus(StrEnum):
    DEFINED = "DEFINED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ReviewVerdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"
    UNCERTAIN = "UNCERTAIN"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _freeze(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class WalkForwardSpec:
    minimum_train_sessions: int = 504
    validation_sessions: int = 63
    test_sessions: int = 63
    step_sessions: int = 63
    embargo_sessions: int = 5

    def __post_init__(self) -> None:
        values = (
            self.minimum_train_sessions,
            self.validation_sessions,
            self.test_sessions,
            self.step_sessions,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise ValueError("walk-forward windows must be integer session counts")
        if not isinstance(self.embargo_sessions, int) or isinstance(self.embargo_sessions, bool):
            raise ValueError("embargo must be an integer session count")
        if min(values) <= 0 or self.embargo_sessions < 0:
            raise ValueError("walk-forward windows must be positive and embargo nonnegative")


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    experiment_id: str
    created_at: datetime
    source_run_ids: tuple[str, ...]
    code_version: str
    config_hashes: tuple[str, ...]
    data_revisions: tuple[str, ...]
    calendar_versions: tuple[str, ...]
    universe_revision: str
    folds: WalkForwardSpec
    metric_version: str
    similarity_config_hash: str
    seed: int
    status: ExperimentStatus = ExperimentStatus.DEFINED

    def __post_init__(self) -> None:
        _aware(self.created_at, "created_at")
        if not self.experiment_id or not self.source_run_ids:
            raise ValueError("experiment ID and source runs are required")
        if len(set(self.source_run_ids)) != len(self.source_run_ids):
            raise ValueError("source runs must be unique")

    @property
    def payload_hash(self) -> str:
        return canonical_hash(self)

    def to_json(self) -> str:
        return canonical_json(self)


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
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
        ordered = (
            self.train_start,
            self.train_end,
            self.validation_start,
            self.validation_end,
            self.test_start,
            self.test_end,
        )
        if self.ordinal < 0 or tuple(sorted(ordered)) != ordered:
            raise ValueError("fold dates must be ordered and ordinal nonnegative")


@dataclass(frozen=True, slots=True)
class UniverseMembership:
    membership_id: str
    symbol: str
    effective_from: date
    effective_to: date | None
    source: str
    source_revision: str

    def __post_init__(self) -> None:
        if not self.symbol or not self.source or not self.source_revision:
            raise ValueError("membership identity and provenance are required")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("membership end cannot precede start")

    @classmethod
    def create(
        cls,
        symbol: str,
        effective_from: date,
        effective_to: date | None,
        source: str,
        source_revision: str,
    ) -> UniverseMembership:
        identity = (symbol, effective_from, effective_to, source, source_revision)
        return cls(
            deterministic_id("universe_membership", identity),
            symbol,
            effective_from,
            effective_to,
            source,
            source_revision,
        )


@dataclass(frozen=True, slots=True)
class ResearchRow:
    row_id: str
    observation_id: str
    symbol: str
    session_date: date
    label_available_at: datetime | None
    outcome_label: str | None
    net_r: Decimal | None
    features: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.label_available_at is not None:
            _aware(self.label_available_at, "label_available_at")
        object.__setattr__(self, "features", _freeze(self.features))


@dataclass(frozen=True, slots=True)
class HumanReview:
    review_id: str
    experiment_id: str
    observation_id: str
    reviewer_id: str
    reviewed_at: datetime
    verdict: ReviewVerdict
    notes: str = ""

    def __post_init__(self) -> None:
        _aware(self.reviewed_at, "reviewed_at")
        if not self.reviewer_id:
            raise ValueError("reviewer ID is required")


def eligible_truth_reviews(reviews: tuple[HumanReview, ...]) -> tuple[HumanReview, ...]:
    return tuple(review for review in reviews if review.verdict is not ReviewVerdict.UNCERTAIN)
