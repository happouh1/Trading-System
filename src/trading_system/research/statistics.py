"""Training-fold descriptive statistics with deterministic bootstrap intervals."""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DescriptiveStatistics:
    count: int
    win_rate: Decimal | None
    mean_net_r: Decimal | None
    median_net_r: Decimal | None
    expectancy_r: Decimal | None
    profit_factor: Decimal | None
    maximum_drawdown_r: Decimal
    p10_net_r: Decimal | None
    p90_net_r: Decimal | None
    p10_mfe_r: Decimal | None
    p90_mfe_r: Decimal | None
    p10_mae_r: Decimal | None
    p90_mae_r: Decimal | None
    mean_ci_low: Decimal | None
    mean_ci_high: Decimal | None


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _quantile(values: tuple[Decimal, ...], probability: Decimal) -> Decimal:
    ordered = tuple(sorted(values))
    position = probability * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _drawdown(values: tuple[Decimal, ...]) -> Decimal:
    equity = Decimal(0)
    peak = Decimal(0)
    maximum = Decimal(0)
    for value in values:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def summarize_returns(
    values: tuple[Decimal, ...],
    *,
    seed: int,
    bootstrap_samples: int = 1000,
    mfe_values: tuple[Decimal, ...] = (),
    mae_values: tuple[Decimal, ...] = (),
) -> DescriptiveStatistics:
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    if not values:
        return DescriptiveStatistics(
            0,
            None,
            None,
            None,
            None,
            None,
            Decimal(0),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    if mfe_values and len(mfe_values) != len(values):
        raise ValueError("MFE count must match return count")
    if mae_values and len(mae_values) != len(values):
        raise ValueError("MAE count must match return count")
    if any(not value.is_finite() for value in (*values, *mfe_values, *mae_values)):
        raise ValueError("returns and excursions must be finite")
    mean = _mean(values)
    gains = sum((value for value in values if value > 0), Decimal(0))
    losses = -sum((value for value in values if value < 0), Decimal(0))
    profit_factor = None if losses == 0 else gains / losses
    generator = random.Random(seed)
    bootstrap = tuple(
        _mean(tuple(values[generator.randrange(len(values))] for _ in values))
        for _sample in range(bootstrap_samples)
    )
    return DescriptiveStatistics(
        len(values),
        Decimal(sum(value > 0 for value in values)) / Decimal(len(values)),
        mean,
        _quantile(values, Decimal("0.50")),
        mean,
        profit_factor,
        _drawdown(values),
        _quantile(values, Decimal("0.10")),
        _quantile(values, Decimal("0.90")),
        _quantile(mfe_values, Decimal("0.10")) if mfe_values else None,
        _quantile(mfe_values, Decimal("0.90")) if mfe_values else None,
        _quantile(mae_values, Decimal("0.10")) if mae_values else None,
        _quantile(mae_values, Decimal("0.90")) if mae_values else None,
        _quantile(bootstrap, Decimal("0.025")),
        _quantile(bootstrap, Decimal("0.975")),
    )
