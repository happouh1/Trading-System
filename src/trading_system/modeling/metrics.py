"""Probability-quality and diagnostic metrics for Phase 3A."""

from __future__ import annotations

import random
from dataclasses import dataclass

from sklearn.metrics import (  # type: ignore[import-untyped]
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)


@dataclass(frozen=True, slots=True)
class ThresholdDiagnostic:
    threshold: float
    precision: float | None
    recall: float | None
    specificity: float | None
    coverage: float
    true_negative: int
    false_positive: int
    false_negative: int
    true_positive: int


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_probability: float
    observed_rate: float


@dataclass(frozen=True, slots=True)
class MetricInterval:
    metric: str
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class ProbabilityMetrics:
    count: int
    prevalence: float
    roc_auc: float | None
    average_precision: float
    log_loss: float
    brier_score: float
    expected_calibration_error: float
    calibration_bins: tuple[CalibrationBin, ...]
    bootstrap_intervals: tuple[MetricInterval, ...]
    diagnostics: tuple[ThresholdDiagnostic, ...]


def _ece(targets: tuple[int, ...], probabilities: tuple[float, ...], bins: int = 10) -> float:
    total = len(targets)
    result = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        selected = [
            position
            for position, value in enumerate(probabilities)
            if lower <= value < upper or (index == bins - 1 and value == 1.0)
        ]
        if selected:
            observed = sum(targets[position] for position in selected) / len(selected)
            predicted = sum(probabilities[position] for position in selected) / len(selected)
            result += len(selected) / total * abs(observed - predicted)
    return result


def _calibration_bins(
    targets: tuple[int, ...], probabilities: tuple[float, ...], bins: int = 10
) -> tuple[CalibrationBin, ...]:
    result: list[CalibrationBin] = []
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        selected = [
            position
            for position, value in enumerate(probabilities)
            if lower <= value < upper or (index == bins - 1 and value == 1.0)
        ]
        if selected:
            result.append(
                CalibrationBin(
                    lower,
                    upper,
                    len(selected),
                    sum(probabilities[position] for position in selected) / len(selected),
                    sum(targets[position] for position in selected) / len(selected),
                )
            )
    return tuple(result)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


def probability_metrics(
    targets: tuple[int, ...],
    probabilities: tuple[float, ...],
    *,
    thresholds: tuple[float, ...] = (0.50, 0.60, 0.70),
    seed: int = 0,
    bootstrap_samples: int = 200,
) -> ProbabilityMetrics:
    if len(targets) != len(probabilities) or not targets:
        raise ValueError("nonempty targets and matching probabilities are required")
    if any(value not in {0, 1} for value in targets):
        raise ValueError("targets must be binary")
    if any(not 0.0 <= value <= 1.0 for value in probabilities):
        raise ValueError("probabilities must be in [0,1]")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    diagnostics: list[ThresholdDiagnostic] = []
    for threshold in thresholds:
        predicted = tuple(int(value >= threshold) for value in probabilities)
        values = confusion_matrix(targets, predicted, labels=[0, 1]).ravel()
        tn, fp, fn, tp = (int(value) for value in values)
        precision = None if tp + fp == 0 else tp / (tp + fp)
        recall = None if tp + fn == 0 else tp / (tp + fn)
        specificity = None if tn + fp == 0 else tn / (tn + fp)
        diagnostics.append(
            ThresholdDiagnostic(
                threshold,
                precision,
                recall,
                specificity,
                sum(value >= threshold for value in probabilities) / len(probabilities),
                tn,
                fp,
                fn,
                tp,
            )
        )
    has_both = set(targets) == {0, 1}
    generator = random.Random(seed)
    brier_samples: list[float] = []
    log_loss_samples: list[float] = []
    for _sample in range(bootstrap_samples):
        indices = tuple(generator.randrange(len(targets)) for _ in targets)
        sample_targets = tuple(targets[index] for index in indices)
        sample_probabilities = tuple(probabilities[index] for index in indices)
        brier_samples.append(float(brier_score_loss(sample_targets, sample_probabilities)))
        log_loss_samples.append(
            float(log_loss(sample_targets, sample_probabilities, labels=[0, 1]))
        )
    return ProbabilityMetrics(
        len(targets),
        sum(targets) / len(targets),
        float(roc_auc_score(targets, probabilities)) if has_both else None,
        float(average_precision_score(targets, probabilities)),
        float(log_loss(targets, probabilities, labels=[0, 1])),
        float(brier_score_loss(targets, probabilities)),
        _ece(targets, probabilities),
        _calibration_bins(targets, probabilities),
        (
            MetricInterval(
                "brier_score", _quantile(brier_samples, 0.025), _quantile(brier_samples, 0.975)
            ),
            MetricInterval(
                "log_loss",
                _quantile(log_loss_samples, 0.025),
                _quantile(log_loss_samples, 0.975),
            ),
        ),
        tuple(diagnostics),
    )
