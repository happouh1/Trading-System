"""Direction-aware fixed-horizon research outcomes for Phase 7E entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_system.domain import Candle, Direction, Timeframe
from trading_system.patterns.range_entry import (
    RangeEntryStatus,
    RangeResearchEntry,
)
from trading_system.patterns.range_outcome_config import RangeOutcomeConfig
from trading_system.patterns.range_reclaim import RangeBox
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class RangeEntryOutcome:
    outcome_id: str
    run_id: str
    entry_id: str
    evidence_id: str
    box_id: str
    symbol: str
    timeframe: Timeframe
    direction: Direction
    horizon_bars: int
    label_available_at: datetime
    exit_candle_id: str
    exit_close: Decimal
    simulated_exit_price: Decimal
    gross_directional_return: Decimal
    net_directional_return: Decimal
    maximum_favorable_box_units: Decimal
    maximum_adverse_box_units: Decimal
    path_candle_ids: tuple[str, ...]
    config_hash: str
    code_version: str
    outcome_version: str = "7F.1.0"

    def __post_init__(self) -> None:
        if not all(
            (
                self.outcome_id, self.run_id, self.entry_id, self.evidence_id, self.box_id,
                self.symbol, self.exit_candle_id, self.config_hash, self.code_version,
            )
        ):
            raise ValueError("complete range outcome identity and provenance are required")
        if self.label_available_at.tzinfo is None or self.label_available_at.utcoffset() is None:
            raise ValueError("label_available_at must be timezone-aware")
        if self.horizon_bars <= 0 or len(self.path_candle_ids) != self.horizon_bars:
            raise ValueError("horizon must match path evidence")
        if len(set(self.path_candle_ids)) != len(self.path_candle_ids):
            raise ValueError("path candle evidence must be unique")
        if self.path_candle_ids[-1] != self.exit_candle_id:
            raise ValueError("exit candle must terminate path evidence")
        for value in (
            self.exit_close, self.simulated_exit_price, self.maximum_favorable_box_units,
            self.maximum_adverse_box_units,
        ):
            if not value.is_finite() or value < 0:
                raise ValueError("outcome prices and excursions must be finite and nonnegative")
        if (
            not self.gross_directional_return.is_finite()
            or not self.net_directional_return.is_finite()
        ):
            raise ValueError("returns must be finite")
        if self.outcome_version != "7F.1.0":
            raise ValueError("outcome_version is fixed for Phase 7F")


def label_range_entries(
    config: RangeOutcomeConfig,
    *,
    entries: tuple[RangeResearchEntry, ...],
    boxes: tuple[RangeBox, ...],
    candles: tuple[Candle, ...],
) -> tuple[RangeEntryOutcome, ...]:
    if len({item.entry_id for item in entries}) != len(entries):
        raise ValueError("entry identities must be unique")
    box_by_id = {item.box_id: item for item in boxes}
    if len(box_by_id) != len(boxes):
        raise ValueError("box identities must be unique")
    if len({item.candle_id for item in candles}) != len(candles):
        raise ValueError("candle identities must be unique")
    results: list[RangeEntryOutcome] = []
    for entry in sorted(entries, key=lambda item: (item.entry_time, item.entry_id)):
        if entry.status is not RangeEntryStatus.FILLED:
            continue
        if entry.simulated_fill_price is None:
            raise ValueError("filled entry lacks a simulated fill")
        box = box_by_id.get(entry.box_id)
        if box is None or box.symbol != entry.symbol or box.timeframe is not entry.timeframe:
            raise ValueError("entry requires its matching range box")
        series = tuple(
            sorted(
                (
                    candle for candle in candles
                    if candle.symbol == entry.symbol and candle.timeframe is entry.timeframe
                ),
                key=lambda candle: (candle.open_time, candle.candle_id),
            )
        )
        source_indexes = [
            index for index, candle in enumerate(series)
            if candle.candle_id == entry.source_candle_id
        ]
        if len(source_indexes) != 1:
            raise ValueError("entry source candle must occur exactly once")
        source_index = source_indexes[0]
        source = series[source_index]
        if source.open_time != entry.entry_time or source.open != entry.opening_price:
            raise ValueError("entry source candle disagrees with recorded entry")
        for horizon in config.horizons(entry.timeframe):
            path = series[source_index : source_index + horizon]
            if len(path) != horizon:
                continue
            if any(not candle.is_complete for candle in path):
                raise ValueError("outcome paths require completed candles")
            exit_candle = path[-1]
            exit_price = (
                exit_candle.close - entry.slippage
                if entry.direction is Direction.LONG
                else exit_candle.close + entry.slippage
            )
            if exit_price <= 0:
                raise ValueError("simulated exit price must remain positive")
            sign = Decimal(1) if entry.direction is Direction.LONG else Decimal(-1)
            gross_return = sign * (exit_candle.close - entry.opening_price) / entry.opening_price
            net_return = (
                sign
                * (exit_price - entry.simulated_fill_price)
                / entry.simulated_fill_price
            )
            width = box.upper - box.lower
            favorable = (
                max(candle.high for candle in path) - entry.simulated_fill_price
                if entry.direction is Direction.LONG
                else entry.simulated_fill_price - min(candle.low for candle in path)
            )
            adverse = (
                entry.simulated_fill_price - min(candle.low for candle in path)
                if entry.direction is Direction.LONG
                else max(candle.high for candle in path) - entry.simulated_fill_price
            )
            path_ids = tuple(candle.candle_id for candle in path)
            identity = (entry.entry_id, horizon, path_ids, config.config_hash, "7F.1.0")
            results.append(
                RangeEntryOutcome(
                    deterministic_id("range_entry_outcome", identity), entry.run_id,
                    entry.entry_id, entry.evidence_id, entry.box_id, entry.symbol,
                    entry.timeframe, entry.direction, horizon, exit_candle.close_time,
                    exit_candle.candle_id, exit_candle.close, exit_price, gross_return,
                    net_return, max(Decimal(0), favorable) / width,
                    max(Decimal(0), adverse) / width, path_ids, config.config_hash,
                    entry.code_version,
                )
            )
    return tuple(sorted(results, key=lambda item: (item.label_available_at, item.outcome_id)))
