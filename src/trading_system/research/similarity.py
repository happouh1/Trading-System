"""Training-fold-only normalization and deterministic weighted similarity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class Normalization:
    means: Mapping[str, Decimal]
    scales: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "means", MappingProxyType(dict(self.means)))
        object.__setattr__(self, "scales", MappingProxyType(dict(self.scales)))


@dataclass(frozen=True, slots=True)
class SimilarityCandidate:
    candidate_id: str
    features: Mapping[str, Decimal | None]


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    candidate_id: str
    distance: Decimal
    available_weight_fraction: Decimal


def fit_normalization(
    training_rows: tuple[Mapping[str, Decimal | None], ...],
    feature_names: tuple[str, ...],
) -> Normalization:
    means: dict[str, Decimal] = {}
    scales: dict[str, Decimal] = {}
    for name in feature_names:
        values = tuple(
            value for row in training_rows if isinstance((value := row.get(name)), Decimal)
        )
        if not values:
            continue
        mean = sum(values, Decimal(0)) / Decimal(len(values))
        variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(
            len(values)
        )
        means[name] = mean
        scales[name] = variance.sqrt() if variance > 0 else Decimal(1)
    return Normalization(means, scales)


def rank_similar(
    query: Mapping[str, Decimal | None],
    candidates: tuple[SimilarityCandidate, ...],
    normalization: Normalization,
    weights: Mapping[str, Decimal],
    *,
    minimum_coverage: Decimal = Decimal("0.60"),
) -> tuple[SimilarityResult, ...]:
    if not Decimal(0) <= minimum_coverage <= Decimal(1):
        raise ValueError("minimum coverage must be in [0,1]")
    if not weights or any(weight <= 0 for weight in weights.values()):
        raise ValueError("feature weights must be positive")
    total_weight = sum(weights.values(), Decimal(0))
    results: list[SimilarityResult] = []
    for candidate in candidates:
        numerator = Decimal(0)
        available = Decimal(0)
        for name, weight in weights.items():
            query_value = query.get(name)
            candidate_value = candidate.features.get(name)
            if not isinstance(query_value, Decimal) or not isinstance(candidate_value, Decimal):
                continue
            if name not in normalization.means or name not in normalization.scales:
                continue
            scale = normalization.scales[name]
            numerator += weight * abs(query_value - candidate_value) / scale
            available += weight
        coverage = available / total_weight
        if coverage >= minimum_coverage and available > 0:
            results.append(
                SimilarityResult(candidate.candidate_id, numerator / available, coverage)
            )
    return tuple(sorted(results, key=lambda item: (item.distance, item.candidate_id)))
