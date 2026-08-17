"""Causal multi-timeframe as-of joins and alignment scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal

from trading_system.domain import Direction, Timeframe
from trading_system.structure import StructureState

_ORDER = (Timeframe.WEEK_1, Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1)
_WEIGHTS = {
    Timeframe.WEEK_1: Decimal("0.35"),
    Timeframe.DAY_1: Decimal("0.35"),
    Timeframe.HOUR_4: Decimal("0.20"),
    Timeframe.HOUR_1: Decimal("0.10"),
}


@dataclass(frozen=True, slots=True)
class TimeframeState:
    timeframe: Timeframe
    close_time: datetime
    candle_id: str
    state: StructureState

    def __post_init__(self) -> None:
        if self.close_time.tzinfo is None or self.close_time.utcoffset() is None:
            raise ValueError("close_time must be timezone-aware")
        if not self.candle_id:
            raise ValueError("candle_id is required")


@dataclass(frozen=True, slots=True)
class MtfSnapshot:
    known_at: datetime
    states: tuple[TimeframeState, ...]

    @property
    def source_candle_ids(self) -> tuple[str, ...]:
        return tuple(item.candle_id for item in self.states)


def asof_join(known_at: datetime, values: list[TimeframeState]) -> MtfSnapshot:
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    selected: list[TimeframeState] = []
    for timeframe in _ORDER:
        eligible = [
            item
            for item in values
            if item.timeframe is timeframe and item.close_time <= known_at
        ]
        if eligible:
            selected.append(max(eligible, key=lambda item: (item.close_time, item.candle_id)))
    return MtfSnapshot(known_at=known_at, states=tuple(selected))


def mtf_score(snapshot: MtfSnapshot, direction: Direction) -> Decimal:
    if direction is Direction.NONE:
        raise ValueError("alignment direction cannot be NONE")
    directional = {
        StructureState.UPTREND: Decimal(1),
        StructureState.DOWNTREND: Decimal(-1),
    }
    sign = Decimal(1) if direction is Direction.LONG else Decimal(-1)
    raw = sum(
        (
            _WEIGHTS[item.timeframe] * directional.get(item.state, Decimal(0))
            for item in snapshot.states
        ),
        Decimal(0),
    )
    return (Decimal(50) + Decimal(50) * raw * sign).quantize(
        Decimal("1"), rounding=ROUND_HALF_EVEN
    )
