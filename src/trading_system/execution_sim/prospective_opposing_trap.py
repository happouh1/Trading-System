"""Offline opposing-trap signal and next-open exit; never broker routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from trading_system.domain import Candle, Direction, PatternEvent, PatternState
from trading_system.serialization import deterministic_id

VERSION = "PROSPECTIVE_OPPOSING_TRAP.1.0"
MIN_CONFIDENCE = Decimal(75)


@dataclass(frozen=True, slots=True)
class OpposingTrapEvidence:
    event: PatternEvent
    confidence: Decimal


@dataclass(frozen=True, slots=True)
class OpposingTrapExitAssessment:
    assessment_id: str
    trade_id: str
    symbol: str
    signal_candle_id: str
    signal_event_id: str
    source_candle_id: str
    event_time: datetime
    known_at: datetime
    status: str
    fill_price: Decimal
    qualifying_completed_trade: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    fees_status: str = field(default="NOT_MODELLED", init=False)


def validate_opposing_trap_signal(
    *, evidence: OpposingTrapEvidence, candle: Candle, received_at: datetime,
) -> None:
    event = evidence.event
    if (
        received_at.tzinfo is None or received_at.utcoffset() != timedelta(0)
        or event.new_state is not PatternState.TRAP_CONFIRMED
        or event.direction is not Direction.SHORT
        or event.symbol != candle.symbol or event.timeframe is not candle.timeframe
        or candle.candle_id not in event.evidence_candle_ids
        or not candle.is_complete
        or not candle.close_time <= event.known_at <= received_at
        or not evidence.confidence.is_finite()
        or not MIN_CONFIDENCE <= evidence.confidence <= 100
        or not event.event_id
    ):
        raise ValueError("invalid or unavailable opposing-trap signal")


def assess_opposing_trap_exit(
    *, trade_id: str, symbol: str, signal_candle_id: str,
    signal_event_id: str, signal_known_at: datetime, signal_confidence: Decimal,
    candle: Candle, atr20: Decimal, feature_known_at: datetime,
    adjustment_factor: Decimal, received_at: datetime, as_of: datetime,
) -> OpposingTrapExitAssessment:
    for value in (signal_known_at, feature_known_at, received_at, as_of):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("UTC timestamps required")
    if (
        not trade_id or not signal_candle_id or not signal_event_id
        or symbol == "AAPL" or candle.symbol != symbol or not candle.is_complete
        or signal_known_at > candle.open_time or feature_known_at > candle.open_time
        or not candle.close_time <= received_at <= as_of
        or candle.adjustment_factor != adjustment_factor
        or not signal_confidence.is_finite()
        or not MIN_CONFIDENCE <= signal_confidence <= 100
        or any(not value.is_finite() or value <= 0 for value in (
            candle.open, atr20, adjustment_factor,
        ))
    ):
        raise ValueError("invalid or unavailable opposing-trap exit evidence")
    with localcontext() as context:
        context.prec = 50
        slippage = max(candle.open / Decimal(10000), Decimal("0.02") * atr20)
        fill = candle.open - slippage
    if not fill.is_finite() or fill <= 0:
        raise ValueError("nonpositive modelled opposing-trap fill")
    identity = (
        VERSION, trade_id, symbol, signal_candle_id, signal_event_id,
        signal_known_at, signal_confidence, candle, atr20, feature_known_at,
        adjustment_factor, received_at,
    )
    return OpposingTrapExitAssessment(
        deterministic_id("sim_opposing_trap_exit", identity), trade_id, symbol,
        signal_candle_id, signal_event_id, candle.candle_id, candle.open_time,
        received_at, "OPPOSING_TRAP_EXIT_MODELLED", fill,
    )
