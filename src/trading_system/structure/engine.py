"""Streaming, causal pivot confirmation and structure state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Candle, Swing, SwingKind, Timeframe
from trading_system.serialization import deterministic_id


class StructureState(StrEnum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class StructureSnapshot:
    symbol: str
    timeframe: Timeframe
    known_at: datetime
    state: StructureState
    confirmed_swings: tuple[Swing, ...]
    new_swings: tuple[Swing, ...]
    swing_labels: tuple[tuple[str, str], ...]
    evidence_candle_ids: tuple[str, ...]


class StructureEngine:
    """Confirm centered pivots only after the complete right-side window exists."""

    def __init__(
        self,
        *,
        left: int = 3,
        right: int = 3,
        equality_tolerance_adr: Decimal = Decimal("0.10"),
    ) -> None:
        if left <= 0 or right <= 0:
            raise ValueError("pivot widths must be positive")
        if equality_tolerance_adr < 0 or not equality_tolerance_adr.is_finite():
            raise ValueError("equality tolerance must be finite and nonnegative")
        self.left = left
        self.right = right
        self.equality_tolerance_adr = equality_tolerance_adr
        self._candles: dict[tuple[str, Timeframe], list[Candle]] = {}
        self._swings: dict[tuple[str, Timeframe], list[Swing]] = {}

    def push(self, candle: Candle, adr20: Decimal | None) -> StructureSnapshot:
        if not candle.is_complete:
            raise ValueError("structure requires completed candles")
        key = (candle.symbol, candle.timeframe)
        candles = self._candles.setdefault(key, [])
        if candles and candle.close_time <= candles[-1].close_time:
            raise ValueError("candles must be pushed in strictly increasing close-time order")
        candles.append(candle)
        swings = self._swings.setdefault(key, [])
        new_swings: list[Swing] = []
        candidate_index = len(candles) - self.right - 1
        if candidate_index >= self.left:
            candidate = candles[candidate_index]
            left = candles[candidate_index - self.left : candidate_index]
            right = candles[candidate_index + 1 : candidate_index + self.right + 1]
            evidence = tuple(
                item.candle_id
                for item in candles[
                    candidate_index - self.left : candidate_index + self.right + 1
                ]
            )
            is_high = candidate.high > max(item.high for item in left) and candidate.high >= max(
                item.high for item in right
            )
            is_low = candidate.low < min(item.low for item in left) and candidate.low <= min(
                item.low for item in right
            )
            for kind, price, matched in (
                (SwingKind.HIGH, candidate.high, is_high),
                (SwingKind.LOW, candidate.low, is_low),
            ):
                if matched:
                    swing = Swing(
                        swing_id=deterministic_id(
                            "swing",
                            (candidate.symbol, candidate.timeframe, kind, candidate.candle_id),
                        ),
                        symbol=candidate.symbol,
                        timeframe=candidate.timeframe,
                        kind=kind,
                        price=price,
                        pivot_time=candidate.close_time,
                        confirmed_at=candle.close_time,
                        evidence_candle_ids=evidence,
                    )
                    swings.append(swing)
                    new_swings.append(swing)
        labels = self._labels(swings, adr20)
        state = self._state(swings, adr20)
        return StructureSnapshot(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            known_at=candle.close_time,
            state=state,
            confirmed_swings=tuple(swings),
            new_swings=tuple(new_swings),
            swing_labels=labels,
            evidence_candle_ids=tuple(item.candle_id for item in candles),
        )

    @staticmethod
    def _by_kind(swings: list[Swing], kind: SwingKind) -> list[Swing]:
        return [swing for swing in swings if swing.kind is kind]

    def _labels(
        self, swings: list[Swing], adr20: Decimal | None
    ) -> tuple[tuple[str, str], ...]:
        if adr20 is None:
            return ()
        tolerance = adr20 * self.equality_tolerance_adr
        result: list[tuple[str, str]] = []
        for kind, higher, lower, equal in (
            (SwingKind.HIGH, "HH", "LH", "EQH"),
            (SwingKind.LOW, "HL", "LL", "EQL"),
        ):
            selected = self._by_kind(swings, kind)
            if len(selected) < 2:
                continue
            prior, current = selected[-2:]
            delta = current.price - prior.price
            label = higher if delta > tolerance else lower if delta < -tolerance else equal
            result.append((current.swing_id, label))
        return tuple(result)

    def _state(self, swings: list[Swing], adr20: Decimal | None) -> StructureState:
        highs = self._by_kind(swings, SwingKind.HIGH)
        lows = self._by_kind(swings, SwingKind.LOW)
        if adr20 is None or len(highs) < 2 or len(lows) < 2:
            return StructureState.UNKNOWN
        tolerance = adr20 * self.equality_tolerance_adr
        high_delta = highs[-1].price - highs[-2].price
        low_delta = lows[-1].price - lows[-2].price
        if high_delta > tolerance and low_delta > tolerance:
            return StructureState.UPTREND
        if high_delta < -tolerance and low_delta < -tolerance:
            return StructureState.DOWNTREND
        if abs(high_delta) <= tolerance and abs(low_delta) <= tolerance:
            return StructureState.RANGE
        return StructureState.TRANSITION
