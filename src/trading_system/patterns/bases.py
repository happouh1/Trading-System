"""Deterministic base detection under the approved Phase 1B policy."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise

from trading_system.domain import Candle
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class BaseBar:
    candle: Candle
    adr20: Decimal
    atr10: Decimal


@dataclass(frozen=True, slots=True)
class BaseCandidate:
    instance_id: str
    start_candle_id: str
    end_candle_id: str
    bars: int
    lower: Decimal
    upper: Decimal
    width_adr: Decimal
    net_drift_adr: Decimal
    overlap_score: Decimal
    atr_compression: Decimal
    lower_touches: int
    upper_touches: int
    quality: Decimal


class BaseDetector:
    def __init__(self, *, min_bars: int = 8, max_bars: int = 40) -> None:
        if min_bars < 2 or max_bars < min_bars:
            raise ValueError("invalid base window bounds")
        self.min_bars, self.max_bars = min_bars, max_bars

    def detect(self, bars: list[BaseBar]) -> BaseCandidate | None:
        candidates: list[BaseCandidate] = []
        for size in range(self.min_bars, min(self.max_bars, len(bars)) + 1):
            window, prior = bars[-size:], bars[:-size]
            if len(prior) < 40:
                continue
            candidate = self._candidate(window, prior[-40:])
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            return None
        start_indexes = {bar.candle.candle_id: index for index, bar in enumerate(bars)}
        return max(
            candidates,
            key=lambda item: (
                item.quality,
                item.bars,
                -start_indexes[item.start_candle_id],
            ),
        )

    def _candidate(self, window: list[BaseBar], prior: list[BaseBar]) -> BaseCandidate | None:
        adr = window[-1].adr20
        if adr <= 0:
            return None
        upper = max(item.candle.high for item in window)
        lower = min(item.candle.low for item in window)
        width = (upper - lower) / adr
        drift = abs(window[-1].candle.close - window[0].candle.close) / adr
        overlaps: list[Decimal] = []
        for left, right in pairwise(window):
            intersection = max(
                Decimal(0),
                min(left.candle.high, right.candle.high)
                - max(left.candle.low, right.candle.low),
            )
            denominator = max(
                min(
                    left.candle.high - left.candle.low,
                    right.candle.high - right.candle.low,
                ),
                Decimal("1e-12"),
            )
            overlaps.append(min(intersection / denominator, Decimal(1)))
        overlap = sum(overlaps, Decimal(0)) / Decimal(len(overlaps))
        ordered = sorted(item.atr10 for item in prior)
        median = (ordered[19] + ordered[20]) / Decimal(2)
        compression = window[-1].atr10 / median if median > 0 else Decimal("Infinity")
        tolerance = Decimal("0.10") * adr
        upper_touches = sum(item.candle.high >= upper - tolerance for item in window)
        lower_touches = sum(item.candle.low <= lower + tolerance for item in window)
        valid = (
            width <= Decimal("1.50")
            and drift <= Decimal("0.50")
            and overlap >= Decimal("0.55")
            and compression <= Decimal("0.85")
            and min(upper_touches, lower_touches) >= 2
        )
        if not valid:
            return None
        duration_score = Decimal(100) * Decimal(len(window) - self.min_bars) / Decimal(
            max(self.max_bars - self.min_bars, 1)
        )
        compression_score = Decimal(100) * max(
            Decimal(0), Decimal(1) - compression / Decimal("0.85")
        )
        touch_score = min(
            Decimal(upper_touches + lower_touches) * Decimal(50), Decimal(100)
        )
        drift_score = Decimal(100) * max(
            Decimal(0), Decimal(1) - drift / Decimal("0.50")
        )
        quality = (
            Decimal("0.25") * duration_score
            + Decimal("0.25") * compression_score
            + Decimal("0.20") * overlap * Decimal(100)
            + Decimal("0.15") * touch_score
            + Decimal("0.15") * drift_score
        )
        identity = tuple(item.candle.candle_id for item in window)
        return BaseCandidate(
            deterministic_id("base_instance", identity),
            identity[0],
            identity[-1],
            len(window),
            lower,
            upper,
            width,
            drift,
            overlap,
            compression,
            lower_touches,
            upper_touches,
            quality,
        )
