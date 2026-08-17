"""Next-eligible-open fills, slippage, and gap cancellation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_system.domain import (
    Candle,
    Direction,
    TradeEvent,
    TradeEventType,
    TradePlan,
)
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class EntryResult:
    event: TradeEvent
    fill_price: Decimal | None
    slippage: Decimal


def execute_next_open(
    *,
    run_id: str,
    trade_id: str,
    plan: TradePlan,
    next_candle: Candle,
    atr20: Decimal,
    adr20: Decimal,
    quantity: Decimal,
    slippage_bps: Decimal = Decimal(1),
    slippage_atr_fraction: Decimal = Decimal("0.02"),
    max_gap_adr: Decimal = Decimal("0.25"),
) -> EntryResult:
    if not next_candle.is_complete:
        raise ValueError("execution requires a completed next candle")
    if next_candle.symbol != plan.symbol or next_candle.timeframe is not plan.timeframe:
        raise ValueError("execution candle must match plan symbol and timeframe")
    if next_candle.open_time < plan.created_at:
        raise ValueError("execution candle cannot precede plan creation")
    if atr20 <= 0 or adr20 <= 0 or quantity <= 0:
        raise ValueError("ATR20, ADR20, and quantity must be positive")
    slip = max(
        slippage_bps / Decimal(10000) * next_candle.open,
        slippage_atr_fraction * atr20,
    )
    adverse_gap = (
        next_candle.open - plan.planned_entry
        if plan.direction is Direction.LONG
        else plan.planned_entry - next_candle.open
    )
    event_identity = (run_id, trade_id, plan.plan_id, next_candle.candle_id)
    if adverse_gap > max_gap_adr * adr20:
        event = TradeEvent(
            trade_event_id=deterministic_id("trade_event", (*event_identity, "cancelled")),
            run_id=run_id,
            trade_id=trade_id,
            event_time=next_candle.open_time,
            event_type=TradeEventType.CANCELLED,
            payload={
                "reason": "ENTRY_GAP_TOO_LARGE",
                "planned_entry": plan.planned_entry,
                "next_open": next_candle.open,
                "gap_adr": adverse_gap / adr20,
            },
        )
        return EntryResult(event, None, slip)
    fill = next_candle.open + slip if plan.direction is Direction.LONG else next_candle.open - slip
    event = TradeEvent(
        trade_event_id=deterministic_id("trade_event", (*event_identity, "filled")),
        run_id=run_id,
        trade_id=trade_id,
        event_time=next_candle.open_time,
        event_type=TradeEventType.ENTRY_FILLED,
        price=fill,
        quantity=quantity,
        payload={
            "plan_id": plan.plan_id,
            "slippage": slip,
            "source_candle_id": next_candle.candle_id,
        },
    )
    return EntryResult(event, fill, slip)
