"""Deterministic stop and queued next-open exit fills."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_system.domain import Candle, Direction, TradeEvent, TradeEventType
from trading_system.risk import PositionState
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class ExitResult:
    event: TradeEvent
    fill_price: Decimal
    slippage: Decimal


def _slippage(price: Decimal, atr20: Decimal, bps: Decimal, atr_fraction: Decimal) -> Decimal:
    if price <= 0 or atr20 <= 0:
        raise ValueError("price and ATR20 must be positive")
    return max(bps / Decimal(10000) * price, atr_fraction * atr20)


def execute_stop_exit(
    *,
    run_id: str,
    trade_id: str,
    state: PositionState,
    stop_candle: Candle,
    atr20: Decimal,
    quantity: Decimal,
    slippage_bps: Decimal = Decimal(1),
    slippage_atr_fraction: Decimal = Decimal("0.02"),
) -> ExitResult:
    stop_hit = (
        stop_candle.low <= state.current_stop
        if state.direction is Direction.LONG
        else stop_candle.high >= state.current_stop
    )
    if not stop_hit:
        raise ValueError("stop was not reached by the supplied candle")
    gap_through = (
        stop_candle.open < state.current_stop
        if state.direction is Direction.LONG
        else stop_candle.open > state.current_stop
    )
    reference = stop_candle.open if gap_through else state.current_stop
    slip = _slippage(reference, atr20, slippage_bps, slippage_atr_fraction)
    fill = reference - slip if state.direction is Direction.LONG else reference + slip
    reason = "GAP_THROUGH_STOP" if gap_through else "STOP_HIT"
    event = TradeEvent(
        trade_event_id=deterministic_id(
            "trade_event", (run_id, trade_id, stop_candle.candle_id, reason)
        ),
        run_id=run_id,
        trade_id=trade_id,
        event_time=stop_candle.open_time if gap_through else stop_candle.close_time,
        event_type=TradeEventType.EXIT_FILLED,
        price=fill,
        quantity=quantity,
        payload={
            "reason": reason,
            "stop": state.current_stop,
            "slippage": slip,
            "source_candle_id": stop_candle.candle_id,
        },
    )
    return ExitResult(event, fill, slip)


def execute_queued_next_open_exit(
    *,
    run_id: str,
    trade_id: str,
    state: PositionState,
    signal_candle: Candle,
    next_candle: Candle,
    atr20: Decimal,
    quantity: Decimal,
    reason: str,
    slippage_bps: Decimal = Decimal(1),
    slippage_atr_fraction: Decimal = Decimal("0.02"),
) -> ExitResult:
    if reason not in {"STRUCTURAL_DAMAGE", "OPPOSING_TRAP", "MAX_HOLD"}:
        raise ValueError("unsupported queued exit reason")
    if next_candle.open_time < signal_candle.close_time:
        raise ValueError("queued exit cannot fill before the signal candle closes")
    series_mismatch = (
        next_candle.symbol != signal_candle.symbol
        or next_candle.timeframe is not signal_candle.timeframe
    )
    if series_mismatch:
        raise ValueError("queued exit candle must match signal series")
    slip = _slippage(next_candle.open, atr20, slippage_bps, slippage_atr_fraction)
    fill = (
        next_candle.open - slip
        if state.direction is Direction.LONG
        else next_candle.open + slip
    )
    event = TradeEvent(
        trade_event_id=deterministic_id(
            "trade_event", (run_id, trade_id, next_candle.candle_id, reason)
        ),
        run_id=run_id,
        trade_id=trade_id,
        event_time=next_candle.open_time,
        event_type=TradeEventType.EXIT_FILLED,
        price=fill,
        quantity=quantity,
        payload={
            "reason": reason,
            "slippage": slip,
            "signal_candle_id": signal_candle.candle_id,
            "source_candle_id": next_candle.candle_id,
        },
    )
    return ExitResult(event, fill, slip)
