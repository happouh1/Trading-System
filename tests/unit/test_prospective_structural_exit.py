from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from tests.unit.test_prospective_entry import OPEN, D, bar
from trading_system.execution_sim.prospective_structural_exit import assess_structural_exit


def test_structural_exit_is_next_open_economic_but_receipt_known() -> None:
    candle = replace(
        bar(), open_time=OPEN + timedelta(hours=1),
        close_time=OPEN + timedelta(hours=2), open=D(102), high=D(103),
        low=D(101), close=D(102), raw_open=D(102), raw_high=D(103),
        raw_low=D(101), raw_close=D(102), candle_id="",
    )
    result = assess_structural_exit(
        trade_id="trade", symbol="MSFT", signal_candle_id="signal",
        signal_known_at=candle.open_time, signal_damage_score=D(70),
        candle=candle, atr20=D(2), feature_known_at=OPEN,
        adjustment_factor=D(1), received_at=candle.close_time,
        as_of=candle.close_time,
    )
    assert result.status == "STRUCTURAL_DAMAGE_EXIT_MODELLED"
    assert result.event_time == candle.open_time
    assert result.known_at == candle.close_time
    assert result.fill_price == D("101.96")
    assert result.fees_status == "NOT_MODELLED"
    assert not result.qualifying_completed_trade and not result.broker_write_performed
    with pytest.raises(ValueError, match="unavailable"):
        assess_structural_exit(
            trade_id="trade", symbol="MSFT", signal_candle_id="signal",
            signal_known_at=candle.open_time + timedelta(seconds=1),
            signal_damage_score=D(70), candle=candle, atr20=D(2),
            feature_known_at=OPEN, adjustment_factor=D(1),
            received_at=candle.close_time, as_of=candle.close_time,
        )
    with pytest.raises(ValueError, match="unavailable"):
        assess_structural_exit(
            trade_id="trade", symbol="MSFT", signal_candle_id="signal",
            signal_known_at=candle.open_time, signal_damage_score=D(69),
            candle=candle, atr20=D(2), feature_known_at=OPEN,
            adjustment_factor=D(1), received_at=candle.close_time,
            as_of=candle.close_time,
        )
