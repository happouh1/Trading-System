"""Offline protective-stop assessment with explicit information availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from trading_system.domain import Candle, Direction
from trading_system.execution_sim.exits import execute_stop_exit
from trading_system.risk import PositionState
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class StopAssessment:
    assessment_id: str
    trade_id: str
    symbol: str
    source_candle_id: str
    event_time: datetime
    known_at: datetime
    status: str
    fill_price: Decimal | None
    qualifying_completed_trade: bool = field(default=False, init=False)
    fees_status: str = field(default="NOT_MODELLED", init=False)


def assess_stop(
    *, trade_id: str, symbol: str, state: PositionState, state_known_at: datetime,
    atr20: Decimal, feature_known_at: datetime, adjustment_factor: Decimal,
    candle: Candle, received_at: datetime, as_of: datetime,
) -> StopAssessment:
    for value in (state_known_at, feature_known_at, received_at, as_of):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("UTC timestamps required")
    if (
        not trade_id or symbol == "AAPL" or candle.symbol != symbol
        or state.direction is not Direction.LONG or not candle.is_complete
        or state_known_at > candle.open_time or feature_known_at > candle.open_time
        or not candle.close_time <= received_at <= as_of
        or candle.adjustment_factor != adjustment_factor
    ):
        raise ValueError("invalid or unavailable stop evidence")
    if any(not value.is_finite() or value <= 0 for value in (
        state.entry, state.initial_stop, state.current_stop, state.risk, atr20, adjustment_factor,
    )) or state.current_stop < state.initial_stop:
        raise ValueError("invalid stop state")
    fill: Decimal | None = None
    at = candle.close_time
    status = "STOP_NOT_HIT"
    if candle.low <= state.current_stop:
        with localcontext() as context:
            context.prec = 50
            result = execute_stop_exit(
                run_id="offline-prospective", trade_id=trade_id, state=state,
                stop_candle=candle, atr20=atr20, quantity=Decimal(1),
            )
        fill, at = result.fill_price, result.event.event_time
        if fill <= 0 or not fill.is_finite():
            raise ValueError("nonpositive modelled stop fill")
        status = "STOP_EXIT_MODELLED"
    return StopAssessment(
        deterministic_id("sim_stop_assessment", (
            "PROSPECTIVE_STOP.1.0", trade_id, symbol, state, state_known_at, atr20,
            feature_known_at, adjustment_factor, candle, received_at,
        )), trade_id, symbol, candle.candle_id, at, received_at, status, fill,
    )
