"""Materialize causal, hypothetical next-open entries for Phase 7D evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Candle, Direction, Timeframe
from trading_system.patterns.range_entry_config import RangeEntryConfig
from trading_system.patterns.range_trigger import RangeReclaimEvidence
from trading_system.serialization import deterministic_id


class RangeEntryStatus(StrEnum):
    FILLED = "FILLED"
    CANCELLED_ADVERSE_GAP = "CANCELLED_ADVERSE_GAP"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RangeEntryContext:
    evidence_id: str
    known_at: datetime
    atr20: Decimal
    adr20: Decimal

    def __post_init__(self) -> None:
        if not self.evidence_id:
            raise ValueError("evidence_id is required")
        _aware(self.known_at, "known_at")
        if any(not value.is_finite() or value <= 0 for value in (self.atr20, self.adr20)):
            raise ValueError("ATR20 and ADR20 must be finite and positive")


@dataclass(frozen=True, slots=True)
class RangeResearchEntry:
    entry_id: str
    run_id: str
    evidence_id: str
    box_id: str
    event_id: str
    symbol: str
    timeframe: Timeframe
    direction: Direction
    status: RangeEntryStatus
    evidence_known_at: datetime
    entry_time: datetime
    source_candle_id: str
    source_revision: str
    reference_level: Decimal
    opening_price: Decimal
    simulated_fill_price: Decimal | None
    slippage: Decimal
    adverse_gap_adr20: Decimal
    atr20: Decimal
    adr20: Decimal
    config_hash: str
    code_version: str
    entry_version: str = "7E.1.0"

    def __post_init__(self) -> None:
        if not all(
            (
                self.entry_id, self.run_id, self.evidence_id, self.box_id, self.event_id,
                self.symbol, self.source_candle_id, self.source_revision, self.config_hash,
                self.code_version,
            )
        ):
            raise ValueError("complete range-entry identity and provenance are required")
        _aware(self.evidence_known_at, "evidence_known_at")
        _aware(self.entry_time, "entry_time")
        if self.entry_time < self.evidence_known_at:
            raise ValueError("entry cannot precede its evidence")
        for value in (
            self.reference_level, self.opening_price, self.slippage, self.atr20, self.adr20
        ):
            if not value.is_finite() or value <= 0:
                raise ValueError("entry prices, volatility, and slippage must be positive")
        if not self.adverse_gap_adr20.is_finite():
            raise ValueError("adverse gap must be finite")
        if self.status is RangeEntryStatus.FILLED and self.simulated_fill_price is None:
            raise ValueError("filled entry requires a simulated price")
        if (
            self.status is RangeEntryStatus.CANCELLED_ADVERSE_GAP
            and self.simulated_fill_price is not None
        ):
            raise ValueError("cancelled entry cannot have a simulated fill")
        if self.entry_version != "7E.1.0":
            raise ValueError("entry_version is fixed for Phase 7E")


def materialize_range_entries(
    config: RangeEntryConfig,
    *,
    evidence: tuple[RangeReclaimEvidence, ...],
    contexts: tuple[RangeEntryContext, ...],
    candles: tuple[Candle, ...],
) -> tuple[RangeResearchEntry, ...]:
    if len({item.evidence_id for item in evidence}) != len(evidence):
        raise ValueError("range evidence identities must be unique")
    context_by_id = {item.evidence_id: item for item in contexts}
    if len(context_by_id) != len(contexts):
        raise ValueError("entry context identities must be unique")
    if set(context_by_id) != {item.evidence_id for item in evidence}:
        raise ValueError("every evidence record requires exactly one entry context")
    ordered_candles = tuple(sorted(candles, key=lambda item: (item.open_time, item.candle_id)))
    if len({item.candle_id for item in ordered_candles}) != len(ordered_candles):
        raise ValueError("candle identities must be unique")
    results: list[RangeResearchEntry] = []
    for item in sorted(evidence, key=lambda value: (value.known_at, value.evidence_id)):
        context = context_by_id[item.evidence_id]
        if context.known_at > item.known_at:
            raise ValueError("entry volatility context is future information")
        next_candle = next(
            (
                candle
                for candle in ordered_candles
                if candle.symbol == item.symbol
                and candle.timeframe is item.timeframe
                and candle.open_time >= item.known_at
            ),
            None,
        )
        if next_candle is None:
            continue
        if not next_candle.is_complete:
            raise ValueError("historical entry proxy requires a completed candle")
        slip = max(
            config.slippage_bps / Decimal(10000) * next_candle.open,
            config.slippage_atr20_fraction * context.atr20,
        )
        adverse_gap = (
            next_candle.open - item.reference_level
            if item.direction is Direction.LONG
            else item.reference_level - next_candle.open
        )
        gap_adr = adverse_gap / context.adr20
        cancelled = gap_adr > config.maximum_adverse_gap_adr20
        fill = None
        if not cancelled:
            fill = (
                next_candle.open + slip
                if item.direction is Direction.LONG
                else next_candle.open - slip
            )
        status = (
            RangeEntryStatus.CANCELLED_ADVERSE_GAP if cancelled else RangeEntryStatus.FILLED
        )
        identity = (
            item.evidence_id, next_candle.candle_id, context, config.config_hash, status,
            "7E.1.0",
        )
        results.append(
            RangeResearchEntry(
                deterministic_id("range_research_entry", identity), item.run_id,
                item.evidence_id, item.box_id, item.event_id, item.symbol, item.timeframe,
                item.direction, status, item.known_at, next_candle.open_time,
                next_candle.candle_id, next_candle.source_revision, item.reference_level,
                next_candle.open, fill, slip, gap_adr, context.atr20, context.adr20,
                config.config_hash, item.code_version,
            )
        )
    return tuple(sorted(results, key=lambda item: (item.entry_time, item.entry_id)))
