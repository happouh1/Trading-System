"""Observed outcome calibration kept separate from rule confidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    observation_id: str
    rule_confidence: Decimal
    succeeded: bool


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower_bound: Decimal
    upper_bound: Decimal
    count: int
    mean_rule_confidence: Decimal
    observed_success_rate: Decimal
    absolute_gap: Decimal


def calibration_report(
    observations: tuple[CalibrationObservation, ...],
    *,
    bin_width: Decimal = Decimal(10),
) -> tuple[CalibrationBin, ...]:
    if bin_width <= 0 or Decimal(100) % bin_width != 0:
        raise ValueError("bin width must divide 100 exactly")
    if any(item.rule_confidence < 0 or item.rule_confidence > 100 for item in observations):
        raise ValueError("rule confidence must be in [0,100]")
    bins: list[CalibrationBin] = []
    lower = Decimal(0)
    while lower < 100:
        upper = lower + bin_width
        selected = tuple(
            item
            for item in observations
            if lower <= item.rule_confidence < upper
            or (upper == 100 and item.rule_confidence == 100)
        )
        if selected:
            mean = sum((item.rule_confidence for item in selected), Decimal(0)) / Decimal(
                len(selected)
            )
            observed = Decimal(sum(item.succeeded for item in selected)) / Decimal(len(selected))
            expected = mean / Decimal(100)
            bins.append(
                CalibrationBin(
                    lower,
                    upper,
                    len(selected),
                    mean,
                    observed,
                    abs(observed - expected),
                )
            )
        lower = upper
    return tuple(bins)
