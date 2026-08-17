from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from tests.unit.test_features import daily_candle
from tests.unit.test_risk import NOW
from trading_system.domain import Direction, Timeframe, TradeEventType, TradePlan
from trading_system.execution_sim import execute_next_open

D = Decimal


def plan(direction: Direction = Direction.LONG) -> TradePlan:
    return TradePlan(
        plan_id="plan-1",
        symbol="AAPL",
        timeframe=Timeframe.DAY_1,
        direction=direction,
        created_at=NOW,
        planned_entry=D("100"),
        initial_stop=D("98") if direction is Direction.LONG else D("102"),
        risk_per_unit=D("2"),
        runway_adr=D("2"),
        reward_risk=D("2"),
        pattern_instance_id="pattern-1",
    )


def test_entry_fills_only_at_later_bar_open_with_adverse_slippage() -> None:
    candle = daily_candle(5)
    result = execute_next_open(
        run_id="run-1",
        trade_id="trade-1",
        plan=plan(),
        next_candle=candle,
        atr20=D("2"),
        adr20=D("4"),
        quantity=D("10"),
    )
    assert result.event.event_type is TradeEventType.ENTRY_FILLED
    assert result.event.event_time == candle.open_time
    assert result.slippage == D("0.04")
    assert result.fill_price == D("100.04")


def test_excessive_directional_gap_cancels_entry() -> None:
    candle = replace(
        daily_candle(5),
        open=D("102"),
        high=D("103"),
        raw_open=D("102"),
        raw_high=D("103"),
        candle_id="",
    )
    result = execute_next_open(
        run_id="run-1",
        trade_id="trade-1",
        plan=plan(),
        next_candle=candle,
        atr20=D("2"),
        adr20=D("4"),
        quantity=D("10"),
    )
    assert result.event.event_type is TradeEventType.CANCELLED
    assert result.fill_price is None
    assert result.event.payload["reason"] == "ENTRY_GAP_TOO_LARGE"


def test_same_close_execution_is_rejected() -> None:
    candle = daily_candle(0)
    with pytest.raises(ValueError, match="precede"):
        execute_next_open(
            run_id="run-1",
            trade_id="trade-1",
            plan=replace(plan(), created_at=candle.close_time),
            next_candle=candle,
            atr20=D("2"),
            adr20=D("4"),
            quantity=D("10"),
        )
