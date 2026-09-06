"""Deterministic cluster-level confirmatory statistics for range research."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType

from trading_system.domain import Direction, Timeframe
from trading_system.serialization import canonical_hash, deterministic_id


class RangeConfirmatoryConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryCohort:
    summary_id: str
    plan_id: str
    fold_id: str
    timeframe: Timeframe
    direction: Direction
    horizon_bars: int
    cluster_returns: tuple[tuple[str, Decimal], ...]

    def __post_init__(self) -> None:
        if not self.summary_id or not self.plan_id or not self.fold_id or self.horizon_bars <= 0:
            raise ValueError("complete confirmatory cohort identity is required")
        cluster_ids = tuple(item[0] for item in self.cluster_returns)
        if cluster_ids != tuple(sorted(cluster_ids)) or len(set(cluster_ids)) != len(cluster_ids):
            raise ValueError("cluster returns must have unique sorted identities")
        if any(
            not cluster_id or not value.is_finite()
            for cluster_id, value in self.cluster_returns
        ):
            raise ValueError("cluster returns must be finite and identified")


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryTest:
    test_id: str
    summary_id: str
    plan_id: str
    fold_id: str
    timeframe: Timeframe
    direction: Direction
    horizon_bars: int
    cluster_count: int
    positive_count: int
    negative_count: int
    zero_count: int
    raw_p_value: Decimal
    holm_adjusted_p_value: Decimal
    familywise_alpha: Decimal
    null_rejected: bool
    config_hash: str
    analysis_version: str = "8A.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.test_id
            or self.cluster_count != self.positive_count + self.negative_count + self.zero_count
            or min(
                self.cluster_count,
                self.positive_count,
                self.negative_count,
                self.zero_count,
            )
            < 0
            or not Decimal("0") <= self.raw_p_value <= Decimal("1")
            or not Decimal("0") <= self.holm_adjusted_p_value <= Decimal("1")
            or not Decimal("0") < self.familywise_alpha < Decimal("1")
            or self.null_rejected != (self.holm_adjusted_p_value <= self.familywise_alpha)
            or self.analysis_version != "8A.1.0"
            or self.production_authority
        ):
            raise ValueError("Phase 8A confirmatory test is invalid")


def load_range_confirmatory_config(path: str | Path) -> RangeConfirmatoryConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "analysis_version",
        "source",
        "method",
        "authority",
    }:
        raise RangeConfirmatoryConfigError("Phase 8A configuration keys are invalid")
    if raw["analysis_version"] != "8A.1.0" or raw["source"] != (
        "PHASE7G_TEST_COHORTS_PASSING_FROZEN_EVIDENCE_GATES"
    ):
        raise RangeConfirmatoryConfigError("Phase 8A source policy is invalid")
    if raw["method"] != {
        "test": "EXACT_ONE_SIDED_CLUSTER_MEAN_SIGN_TEST",
        "alternative": "POSITIVE",
        "cluster_unit": "BOX_ID",
        "zero_treatment": "EXCLUDE_FROM_SIGN_COUNT",
        "multiple_testing_correction": "HOLM",
        "alpha_source": "PHASE7C_FROZEN_FAMILYWISE_ALPHA",
    }:
        raise RangeConfirmatoryConfigError("Phase 8A statistical method is invalid")
    authority = raw["authority"]
    expected = {
        "efficacy_claims_enabled", "parameter_selection_enabled", "scoring_enabled",
        "decision_changes_enabled", "alerts_enabled", "options_routing_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != expected or any(
        value is not False for value in authority.values()
    ):
        raise RangeConfirmatoryConfigError("Phase 8A authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeConfirmatoryConfig(MappingProxyType(frozen), canonical_hash(raw))


def exact_positive_sign_p_value(positive: int, negative: int) -> Decimal:
    if min(positive, negative) < 0:
        raise ValueError("sign counts cannot be negative")
    trials = positive + negative
    if trials == 0:
        return Decimal("1")
    numerator = sum(math.comb(trials, value) for value in range(positive, trials + 1))
    with localcontext() as context:
        context.prec = 50
        return Decimal(numerator) / Decimal(2**trials)


def holm_adjust(raw_values: tuple[tuple[str, Decimal], ...]) -> Mapping[str, Decimal]:
    if len({identity for identity, _ in raw_values}) != len(raw_values):
        raise ValueError("hypothesis identities must be unique")
    if any(value < 0 or value > 1 for _, value in raw_values):
        raise ValueError("p-values must be within zero and one")
    ordered = sorted(raw_values, key=lambda item: (item[1], item[0]))
    adjusted: dict[str, Decimal] = {}
    running = Decimal("0")
    family_size = len(ordered)
    for ordinal, (identity, raw) in enumerate(ordered):
        candidate = min(Decimal("1"), raw * Decimal(family_size - ordinal))
        running = max(running, candidate)
        adjusted[identity] = running
    return MappingProxyType(adjusted)


def evaluate_confirmatory_family(
    config: RangeConfirmatoryConfig,
    *,
    cohorts: tuple[RangeConfirmatoryCohort, ...],
    familywise_alpha: Decimal,
) -> tuple[RangeConfirmatoryTest, ...]:
    if not Decimal("0") < familywise_alpha < Decimal("1"):
        raise ValueError("familywise alpha must be between zero and one")
    ordered = tuple(sorted(cohorts, key=lambda item: item.summary_id))
    if len({item.summary_id for item in ordered}) != len(ordered):
        raise ValueError("confirmatory cohort identities must be unique")
    counts: dict[str, tuple[int, int, int]] = {}
    raw: list[tuple[str, Decimal]] = []
    for cohort in ordered:
        positive = sum(value > 0 for _, value in cohort.cluster_returns)
        negative = sum(value < 0 for _, value in cohort.cluster_returns)
        zero = len(cohort.cluster_returns) - positive - negative
        counts[cohort.summary_id] = (positive, negative, zero)
        raw.append((cohort.summary_id, exact_positive_sign_p_value(positive, negative)))
    adjusted = holm_adjust(tuple(raw))
    raw_by_id = dict(raw)
    results: list[RangeConfirmatoryTest] = []
    for cohort in ordered:
        positive, negative, zero = counts[cohort.summary_id]
        adjusted_p = adjusted[cohort.summary_id]
        identity = (
            cohort, raw_by_id[cohort.summary_id], adjusted_p, familywise_alpha,
            config.config_hash, "8A.1.0",
        )
        results.append(
            RangeConfirmatoryTest(
                deterministic_id("range_confirmatory_test", identity), cohort.summary_id,
                cohort.plan_id, cohort.fold_id, cohort.timeframe, cohort.direction,
                cohort.horizon_bars, len(cohort.cluster_returns), positive, negative, zero,
                raw_by_id[cohort.summary_id], adjusted_p, familywise_alpha,
                adjusted_p <= familywise_alpha, config.config_hash,
            )
        )
    return tuple(results)
