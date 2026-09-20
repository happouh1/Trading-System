from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from tests.unit.test_prospective_entry import OPEN, D, bar
from trading_system.execution_sim.prospective_max_hold import assess_max_hold


def test_max_hold_uses_next_open_but_only_completed_receipt_is_known() -> None:
    candle = replace(
        bar(), open_time=OPEN + timedelta(hours=1),
        close_time=OPEN + timedelta(hours=2), open=D(105), high=D(106),
        low=D(104), close=D(105), raw_open=D(105), raw_high=D(106),
        raw_low=D(104), raw_close=D(105), candle_id="",
    )
    result = assess_max_hold(
        trade_id="trade", symbol="MSFT", signal_candle_id="signal",
        signal_known_at=candle.open_time, candle=candle, atr20=D(2),
        feature_known_at=candle.open_time, adjustment_factor=D(1),
        received_at=candle.close_time, as_of=candle.close_time,
    )
    assert result.status == "MAX_HOLD_EXIT_MODELLED"
    assert result.event_time == candle.open_time
    assert result.known_at == candle.close_time
    assert result.fill_price == D("104.96")
    assert result.fees_status == "NOT_MODELLED"
    assert not result.qualifying_completed_trade and not result.broker_write_performed
    with pytest.raises(ValueError, match="unavailable"):
        assess_max_hold(
            trade_id="trade", symbol="MSFT", signal_candle_id="signal",
            signal_known_at=candle.open_time, candle=candle, atr20=D(2),
            feature_known_at=candle.open_time + timedelta(seconds=1),
            adjustment_factor=D(1), received_at=candle.close_time, as_of=candle.close_time,
        )
