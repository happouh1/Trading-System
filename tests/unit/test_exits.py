from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from tests.unit.test_features import daily_candle
from tests.unit.test_positions import position
from trading_system.execution_sim import execute_queued_next_open_exit, execute_stop_exit

D = Decimal


def test_gap_through_long_stop_uses_open_and_adverse_slippage() -> None:
    candle = replace(
        daily_candle(2),
        open=D("97"),
        high=D("99"),
        low=D("96"),
        close=D("97.5"),
        raw_open=D("97"),
        raw_high=D("99"),
        raw_low=D("96"),
        raw_close=D("97.5"),
        candle_id="",
    )
    result = execute_stop_exit(
        run_id="run-1",
        trade_id="trade-1",
        state=position(),
        stop_candle=candle,
        atr20=D("2"),
        quantity=D("10"),
    )
    assert result.fill_price == D("96.96")
    assert result.event.event_time == candle.open_time
    assert result.event.payload["reason"] == "GAP_THROUGH_STOP"


def test_structural_damage_exit_fills_only_at_next_open() -> None:
    signal = daily_candle(2)
    next_candle = daily_candle(3)
    result = execute_queued_next_open_exit(
        run_id="run-1",
        trade_id="trade-1",
        state=replace(position(), exit_queued=True),
        signal_candle=signal,
        next_candle=next_candle,
        atr20=D("2"),
        quantity=D("10"),
        reason="STRUCTURAL_DAMAGE",
    )
    assert result.event.event_time == next_candle.open_time
    assert result.fill_price == D("99.96")
