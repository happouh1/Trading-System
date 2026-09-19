from __future__ import annotations

from dataclasses import replace

import pytest

from tests.unit.test_prospective_entry import OPEN, D, bar
from trading_system.domain import Direction
from trading_system.execution_sim.prospective_stop import assess_stop
from trading_system.risk import PositionState


def test_stop_receipt_and_adverse_price() -> None:
    state = PositionState(Direction.LONG, D(100), D(99), D(99), D(1), D(101))
    result = assess_stop(
        trade_id="t", symbol="MSFT", state=state, state_known_at=OPEN,
        atr20=D(2), feature_known_at=OPEN, adjustment_factor=D(1),
        candle=bar(), received_at=bar().close_time, as_of=bar().close_time,
    )
    assert result.fill_price == D("98.96")
    assert result.known_at == bar().close_time
    assert not result.qualifying_completed_trade
    with pytest.raises(ValueError, match="unavailable"):
        assess_stop(
            trade_id="t", symbol="MSFT", state=state, state_known_at=bar().close_time,
            atr20=D(2), feature_known_at=OPEN, adjustment_factor=D(1),
            candle=bar(), received_at=bar().close_time, as_of=bar().close_time,
        )


def test_gap_stop_uses_open_but_is_known_at_receipt() -> None:
    candle = replace(bar(), open=D(98), low=D(97), raw_open=D(98), raw_low=D(97), candle_id="")
    state = PositionState(Direction.LONG, D(100), D(99), D(99), D(1), D(101))
    result = assess_stop(
        trade_id="t", symbol="MSFT", state=state, state_known_at=OPEN,
        atr20=D(2), feature_known_at=OPEN, adjustment_factor=D(1),
        candle=candle, received_at=candle.close_time, as_of=candle.close_time,
    )
    assert result.fill_price == D("97.96")
    assert result.event_time == OPEN and result.known_at == candle.close_time
