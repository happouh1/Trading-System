"""Offline Phase 8G statistical reference kernel with no operational authority."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.research.range_confirmatory import (
    exact_positive_sign_p_value,
    holm_adjust,
)
from trading_system.serialization import canonical_hash, deterministic_id


class RangeReplicationStatisticsConfigError(ValueError):
    """Raised when the immutable Phase 8G kernel policy is widened or malformed."""


class ReplicationState(StrEnum):
    REPLICATED = "REPLICATED"
    NOT_REPLICATED = "NOT_REPLICATED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class RangeReplicationStatisticsConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeReplicationHypothesis:
    hypothesis_id: str
    cluster_returns: tuple[tuple[str, Decimal], ...]
    validity_failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        cluster_ids = tuple(identity for identity, _ in self.cluster_returns)
        if (
            not self.hypothesis_id
            or cluster_ids != tuple(sorted(cluster_ids))
            or len(cluster_ids) != len(set(cluster_ids))
            or any(
                not identity or not value.is_finite()
                for identity, value in self.cluster_returns
            )
            or self.validity_failures != tuple(sorted(set(self.validity_failures)))
            or any(not reason for reason in self.validity_failures)
        ):
            raise ValueError("invalid Phase 8G hypothesis")


@dataclass(frozen=True, slots=True)
class RangeReplicationResult:
    result_id: str
    hypothesis_id: str
    cluster_count: int
    nonzero_cluster_count: int
    median_net_r: Decimal
    lower_confidence_bound_net_r: Decimal | None
    economic_threshold_net_r: Decimal
    raw_p_value: Decimal
    holm_adjusted_p_value: Decimal
    familywise_alpha: Decimal
    state: ReplicationState
    reason_codes: tuple[str, ...]
    config_hash: str
    analysis_version: str = "8G.1.0"
    efficacy_claimed: bool = False
    parameter_selection_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.result_id
            or not self.hypothesis_id
            or self.cluster_count < 0
            or not 0 <= self.nonzero_cluster_count <= self.cluster_count
            or not self.median_net_r.is_finite()
            or (
                self.lower_confidence_bound_net_r is not None
                and not self.lower_confidence_bound_net_r.is_finite()
            )
            or not self.economic_threshold_net_r.is_finite()
            or self.economic_threshold_net_r <= 0
            or not Decimal(0) <= self.raw_p_value <= Decimal(1)
            or not Decimal(0) <= self.holm_adjusted_p_value <= Decimal(1)
            or not Decimal(0) < self.familywise_alpha < Decimal(1)
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not self.config_hash.startswith("sha256:")
            or self.analysis_version != "8G.1.0"
            or self.efficacy_claimed
            or self.parameter_selection_performed
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8G result")


def load_range_replication_statistics_config(
    path: str | Path,
) -> RangeReplicationStatisticsConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "analysis_version",
        "source",
        "method",
        "prerequisites",
        "authority",
    }:
        raise RangeReplicationStatisticsConfigError("Phase 8G configuration keys are invalid")
    if raw["analysis_version"] != "8G.1.0" or raw["source"] != (
        "INDEPENDENTLY_ATTESTED_REGISTERED_PHASE8F_PROTOCOL_REQUIRED"
    ):
        raise RangeReplicationStatisticsConfigError("Phase 8G source policy is invalid")
    if raw["method"] != {
        "effect_estimator": "MEDIAN_BOX_ID_MEAN_NET_DIRECTIONAL_RETURN",
        "effect_interval": "EXACT_ONE_SIDED_ORDER_STATISTIC_LOWER_BOUND",
        "interval_multiplicity": "BONFERRONI_COMPLETE_FAMILY",
        "hypothesis_test": "PHASE8A_EXACT_ONE_SIDED_SIGN_TEST",
        "test_multiplicity": "HOLM_COMPLETE_FAMILY",
        "pooling": "PROHIBITED",
    }:
        raise RangeReplicationStatisticsConfigError("Phase 8G method policy is invalid")
    prerequisites = raw["prerequisites"]
    expected_prerequisites = {
        "real_protocol_required",
        "reviewer_placeholders_forbidden",
        "independent_review_attestation_required",
        "trusted_timestamp_required",
        "unseen_dataset_attestation_required",
    }
    if (
        not isinstance(prerequisites, dict)
        or set(prerequisites) != expected_prerequisites
        or any(value is not True for value in prerequisites.values())
    ):
        raise RangeReplicationStatisticsConfigError("Phase 8G prerequisites must remain strict")
    authority = raw["authority"]
    expected_authority = {
        "cli_enabled",
        "persistence_enabled",
        "real_dataset_access_enabled",
        "efficacy_claims_enabled",
        "parameter_selection_enabled",
        "ranking_enabled",
        "alerts_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise RangeReplicationStatisticsConfigError("Phase 8G authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeReplicationStatisticsConfig(MappingProxyType(frozen), canonical_hash(raw))


def decimal_median(values: tuple[Decimal, ...]) -> Decimal:
    if not values or any(not value.is_finite() for value in values):
        raise ValueError("median requires finite observations")
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)


def exact_median_lower_bound(
    values: tuple[Decimal, ...],
    *,
    one_sided_alpha: Decimal,
) -> Decimal | None:
    """Return the largest order-statistic lower bound meeting exact binomial coverage."""
    if (
        not values
        or any(not value.is_finite() for value in values)
        or not Decimal(0) < one_sided_alpha < Decimal(1)
    ):
        raise ValueError("exact median bound inputs are invalid")
    target_coverage = Decimal(1) - one_sided_alpha
    sample_size = len(values)
    selected_index: int | None = None
    with localcontext() as context:
        context.prec = 50
        denominator = Decimal(2**sample_size)
        for index in range(1, sample_size + 1):
            coverage = Decimal(
                sum(math.comb(sample_size, count) for count in range(index, sample_size + 1))
            ) / denominator
            if coverage >= target_coverage:
                selected_index = index
            else:
                break
    if selected_index is None:
        return None
    return sorted(values)[selected_index - 1]


def evaluate_replication_family(
    config: RangeReplicationStatisticsConfig,
    *,
    hypotheses: tuple[RangeReplicationHypothesis, ...],
    familywise_alpha: Decimal,
    economic_threshold_net_r: Decimal,
    minimum_total_clusters: int,
    minimum_nonzero_clusters: int,
) -> tuple[RangeReplicationResult, ...]:
    """Evaluate already validated synthetic/reviewed inputs without granting authority."""
    if (
        not hypotheses
        or not Decimal(0) < familywise_alpha < Decimal(1)
        or not economic_threshold_net_r.is_finite()
        or economic_threshold_net_r <= 0
        or minimum_total_clusters <= 0
        or minimum_nonzero_clusters <= 0
        or minimum_nonzero_clusters > minimum_total_clusters
    ):
        raise ValueError("Phase 8G family controls are invalid")
    ordered = tuple(sorted(hypotheses, key=lambda item: item.hypothesis_id))
    if len({item.hypothesis_id for item in ordered}) != len(ordered):
        raise ValueError("Phase 8G hypothesis identities must be unique")
    raw_values: list[tuple[str, Decimal]] = []
    for hypothesis in ordered:
        positive = sum(value > 0 for _, value in hypothesis.cluster_returns)
        negative = sum(value < 0 for _, value in hypothesis.cluster_returns)
        raw_values.append(
            (hypothesis.hypothesis_id, exact_positive_sign_p_value(positive, negative))
        )
    adjusted = holm_adjust(tuple(raw_values))
    raw_by_id = dict(raw_values)
    interval_alpha = familywise_alpha / Decimal(len(ordered))
    results: list[RangeReplicationResult] = []
    for hypothesis in ordered:
        values = tuple(value for _, value in hypothesis.cluster_returns)
        cluster_count = len(values)
        nonzero_count = sum(value != 0 for value in values)
        median = decimal_median(values) if values else Decimal(0)
        lower_bound = (
            exact_median_lower_bound(values, one_sided_alpha=interval_alpha)
            if values
            else None
        )
        reasons = set(hypothesis.validity_failures)
        if cluster_count < minimum_total_clusters:
            reasons.add("INSUFFICIENT_TOTAL_CLUSTERS")
        if nonzero_count < minimum_nonzero_clusters:
            reasons.add("INSUFFICIENT_NONZERO_CLUSTERS")
        if lower_bound is None:
            reasons.add("NONTRIVIAL_INTERVAL_UNAVAILABLE")
        adjusted_p = adjusted[hypothesis.hypothesis_id]
        if reasons:
            state = ReplicationState.INCONCLUSIVE
        elif adjusted_p <= familywise_alpha and lower_bound is not None and (
            lower_bound > economic_threshold_net_r
        ):
            state = ReplicationState.REPLICATED
        else:
            state = ReplicationState.NOT_REPLICATED
        reason_codes = tuple(sorted(reasons))
        identity = (
            hypothesis,
            familywise_alpha,
            economic_threshold_net_r,
            minimum_total_clusters,
            minimum_nonzero_clusters,
            median,
            lower_bound,
            raw_by_id[hypothesis.hypothesis_id],
            adjusted_p,
            state,
            reason_codes,
            config.config_hash,
            "8G.1.0",
        )
        results.append(
            RangeReplicationResult(
                deterministic_id("range_replication_result", identity),
                hypothesis.hypothesis_id,
                cluster_count,
                nonzero_count,
                median,
                lower_bound,
                economic_threshold_net_r,
                raw_by_id[hypothesis.hypothesis_id],
                adjusted_p,
                familywise_alpha,
                state,
                reason_codes,
                config.config_hash,
            )
        )
    return tuple(results)
