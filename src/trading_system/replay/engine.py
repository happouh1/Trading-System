"""Causal, resumable replay ordering without strategy-specific behavior."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from trading_system.domain import Candle, Timeframe
from trading_system.serialization import canonical_hash

_TIMEFRAME_ORDER = {
    Timeframe.WEEK_1: 0,
    Timeframe.DAY_1: 1,
    Timeframe.HOUR_4: 2,
    Timeframe.HOUR_1: 3,
}


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    candle: Candle
    output: object


@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    last_close_time: datetime
    processed_candles: int
    state_hash: str


class ReplayEngine:
    """Normalize complete candles and invoke a causal evaluator exactly once per candle."""

    def __init__(self, evaluator: Callable[[Candle], object]) -> None:
        self._evaluator = evaluator

    @staticmethod
    def normalize(candles: Iterable[Candle]) -> tuple[Candle, ...]:
        items = tuple(candles)
        if any(not candle.is_complete for candle in items):
            raise ValueError("replay accepts completed candles only")
        keys = [(c.symbol, c.timeframe, c.open_time, c.source_revision) for c in items]
        if len(keys) != len(set(keys)):
            raise ValueError("replay input contains duplicate candle keys")
        return tuple(
            sorted(
                items,
                key=lambda candle: (
                    candle.close_time,
                    _TIMEFRAME_ORDER[candle.timeframe],
                    candle.symbol,
                    candle.open_time,
                    candle.candle_id,
                ),
            )
        )

    def run(
        self,
        candles: Iterable[Candle],
        *,
        resume_after: datetime | None = None,
        processed_before: int = 0,
    ) -> tuple[tuple[ReplayRecord, ...], ReplayCheckpoint | None]:
        ordered = self.normalize(candles)
        selected = tuple(
            candle
            for candle in ordered
            if resume_after is None or candle.close_time > resume_after
        )
        records = tuple(ReplayRecord(candle, self._evaluator(candle)) for candle in selected)
        if not records:
            return records, None
        count = processed_before + len(records)
        checkpoint = ReplayCheckpoint(
            last_close_time=records[-1].candle.close_time,
            processed_candles=count,
            state_hash=canonical_hash(
                {
                    "processed_candles": count,
                    "candle_ids": tuple(record.candle.candle_id for record in records),
                    "outputs": tuple(record.output for record in records),
                }
            ),
        )
        return records, checkpoint
