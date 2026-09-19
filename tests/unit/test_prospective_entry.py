from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from trading_system.domain import Candle, Direction, Timeframe, TradePlan
from trading_system.execution_sim.prospective import ProspectiveEntry, assess_entry, eligible_slot
from trading_system.market_data.calendar import StaticSessionCalendar

D = Decimal
OPEN = datetime(2026, 9, 21, 13, 30, tzinfo=UTC)
CAL = StaticSessionCalendar({date(2026, 9, 21): (OPEN, OPEN + timedelta(hours=6, minutes=30))})


def entry() -> ProspectiveEntry:
    plan = TradePlan(
        plan_id="p", symbol="MSFT", timeframe=Timeframe.HOUR_1, direction=Direction.LONG,
        created_at=OPEN, planned_entry=D(100), initial_stop=D(98), risk_per_unit=D(2),
        runway_adr=D(2), reward_risk=D(2), pattern_instance_id="pattern",
    )
    return ProspectiveEntry("decision", plan, OPEN, OPEN, D(2), D(4), D(1), "hash", "code")


def bar() -> Candle:
    return Candle(
        symbol="MSFT", timeframe=Timeframe.HOUR_1, open_time=OPEN,
        close_time=OPEN + timedelta(hours=1), session_date=OPEN.date(),
        open=D(100), high=D(101), low=D(99), close=D(100), volume=D(100),
        is_complete=True, adjustment_factor=D(1), source="fixture", source_revision="v1",
        raw_open=D(100), raw_high=D(101), raw_low=D(99), raw_close=D(100), raw_volume=D(100),
    )


def test_receipt_separates_economic_time_from_knowledge() -> None:
    candle = bar()
    received = candle.close_time + timedelta(seconds=4)
    result = assess_entry(
        entry(), calendar=CAL, candle=candle, received_at=received, as_of=received,
    )
    assert result.event_time == OPEN
    assert result.known_at == received
    assert result.fill_price == D("100.04")
    assert result.quantity == 1
    assert result.fees_status == "NOT_MODELLED"
    assert not result.qualifying_completed_trade and not result.broker_write_performed
    assert result == assess_entry(
        entry(), calendar=CAL, candle=candle, received_at=received, as_of=received,
    )
    with pytest.raises(ValueError, match="unavailable"):
        assess_entry(entry(), calendar=CAL, candle=candle, received_at=received, as_of=OPEN)


def test_missing_bar_and_late_decision_do_not_shift_execution() -> None:
    assert assess_entry(entry(), calendar=CAL, as_of=OPEN).status == "WAITING"
    assert assess_entry(entry(), calendar=CAL, as_of=bar().close_time).status.startswith("EXPIRED")
    late = replace(entry(), recorded_at=OPEN + timedelta(seconds=1))
    result = assess_entry(late, calendar=CAL, as_of=bar().close_time)
    assert result.status == "REJECTED_LATE_DECISION"
    later = replace(bar(), open_time=OPEN + timedelta(hours=1),
                    close_time=OPEN + timedelta(hours=2), candle_id="")
    with pytest.raises(ValueError, match="exact"):
        assess_entry(entry(), calendar=CAL, candle=later,
                     received_at=later.close_time, as_of=later.close_time)


def test_partial_final_four_hour_slot() -> None:
    e = entry()
    at = OPEN + timedelta(hours=4)
    e = replace(e, plan=replace(e.plan, timeframe=Timeframe.HOUR_4, created_at=at), recorded_at=at)
    assert eligible_slot(e, CAL) == (at, OPEN + timedelta(hours=6, minutes=30))


@pytest.mark.parametrize("symbol,direction", [("AAPL", Direction.LONG), ("MSFT", Direction.SHORT)])
def test_excluded_scope(symbol: str, direction: Direction) -> None:
    e = entry()
    with pytest.raises(ValueError):
        replace(e, plan=replace(e.plan, symbol=symbol, direction=direction))


def test_gap_and_corporate_action_rejection() -> None:
    candle = replace(
        bar(), open=D(102), high=D(103), raw_open=D(102), raw_high=D(103), candle_id="",
    )
    result = assess_entry(entry(), calendar=CAL, candle=candle,
                          received_at=candle.close_time, as_of=candle.close_time)
    assert result.status == "ENTRY_GAP_TOO_LARGE" and result.fill_price is None
    with pytest.raises(ValueError, match="adjustment"):
        assess_entry(replace(entry(), adjustment_factor=D(2)), calendar=CAL, candle=bar(),
                     received_at=bar().close_time, as_of=bar().close_time)


def test_nonfinite_and_future_features_rejected() -> None:
    with pytest.raises(ValueError):
        replace(entry(), atr20=D("NaN"))
    with pytest.raises(ValueError):
        replace(entry(), feature_known_at=OPEN + timedelta(seconds=1))
