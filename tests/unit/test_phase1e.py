from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from tests.unit.test_decisions import NOW, candidate
from tests.unit.test_features import daily_candle
from trading_system.decisions import DecisionEngine
from trading_system.domain import Candle, Direction, Timeframe, TradeEventType
from trading_system.replay.lifecycle import ReplayTradeLifecycle
from trading_system.replay.outcomes import ReplayOutcomeTracker

D = Decimal


def execution_candle(index: int, *, stop_hit: bool = False) -> Candle:
    source = daily_candle(index)
    open_time = NOW + timedelta(hours=index + 1)
    return replace(
        source,
        timeframe=Timeframe.HOUR_1,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=D("100"),
        high=D("101"),
        low=D("98") if stop_hit else D("99.5"),
        close=D("100.5"),
        raw_open=D("100"),
        raw_high=D("101"),
        raw_low=D("98") if stop_hit else D("99.5"),
        raw_close=D("100.5"),
        candle_id="",
    )


def test_lifecycle_fills_next_open_then_completes_stop_exit() -> None:
    selected = replace(candidate(Direction.LONG), atr20=D("1"), adr20=D("2"))
    decision = DecisionEngine("run-1").decide("observation-1", NOW, (selected,))
    lifecycle = ReplayTradeLifecycle("run-1")
    signal = execution_candle(0)

    plan_events, _ = lifecycle.after_bar(signal, decision, (selected,))
    assert tuple(event.event_type for event in plan_events) == (
        TradeEventType.PLAN_CREATED,
    )
    assert lifecycle.has_exposure(signal)

    entry_events, entry_trades = lifecycle.before_bar(execution_candle(1))
    assert entry_trades == ()
    assert tuple(event.event_type for event in entry_events) == (
        TradeEventType.ENTRY_FILLED,
    )

    exit_events, trades = lifecycle.before_bar(execution_candle(2, stop_hit=True))
    assert tuple(event.event_type for event in exit_events) == (
        TradeEventType.EXIT_FILLED,
    )
    assert len(trades) == 1
    assert trades[0].exit_time == exit_events[0].event_time
    assert trades[0].mfe_r > 0
    assert trades[0].mae_r > 0
    assert not lifecycle.has_exposure(signal)


def test_lifecycle_rejects_a_second_plan_for_same_series() -> None:
    selected = replace(candidate(Direction.LONG), atr20=D("1"), adr20=D("2"))
    decision = DecisionEngine("run-1").decide("observation-1", NOW, (selected,))
    lifecycle = ReplayTradeLifecycle("run-1")
    signal = execution_candle(0)
    lifecycle.after_bar(signal, decision, (selected,))

    lifecycle.after_bar(signal, decision, (selected,))
    entry_events, _ = lifecycle.before_bar(execution_candle(1))
    assert len(entry_events) == 1


def test_outcome_tracker_waits_for_future_completed_bar() -> None:
    selected = replace(candidate(Direction.LONG), atr20=D("1"), adr20=D("2"))
    engine = DecisionEngine("run-1")
    signal = engine.decide("observation-1", NOW, (selected,))
    tracker = ReplayOutcomeTracker("run-1")

    assert tracker.push(execution_candle(0), signal) == ()
    no_trade = engine.decide("observation-2", NOW + timedelta(hours=1), ())
    outcomes = tracker.push(execution_candle(1), no_trade)

    assert tuple(outcome.horizon_bars for outcome in outcomes) == (1,)
    assert outcomes[0].label_available_at == execution_candle(1).close_time


def test_lifecycle_warm_replay_matches_uninterrupted_pending_trade() -> None:
    selected = replace(candidate(Direction.LONG), atr20=D("1"), adr20=D("2"))
    engine = DecisionEngine("run-1")
    signal = engine.decide("observation-1", NOW, (selected,))
    no_trade = engine.decide("observation-2", NOW + timedelta(hours=1), ())
    candles = (
        execution_candle(0),
        execution_candle(1),
        execution_candle(2, stop_hit=True),
    )

    uninterrupted = ReplayTradeLifecycle("run-1")
    uninterrupted.after_bar(candles[0], signal, (selected,))
    full_entry = uninterrupted.before_bar(candles[1])
    uninterrupted.after_bar(candles[1], no_trade, ())
    full_exit = uninterrupted.before_bar(candles[2])

    resumed = ReplayTradeLifecycle("run-1")
    resumed.after_bar(candles[0], signal, (selected,))
    resumed_entry = resumed.before_bar(candles[1])
    resumed.after_bar(candles[1], no_trade, ())
    resumed_exit = resumed.before_bar(candles[2])

    assert resumed_entry == full_entry
    assert resumed_exit == full_exit


def test_removing_later_future_bars_cannot_change_available_outcome() -> None:
    selected = replace(candidate(Direction.LONG), atr20=D("1"), adr20=D("2"))
    engine = DecisionEngine("run-1")
    signal = engine.decide("observation-1", NOW, (selected,))
    no_trade = engine.decide("observation-2", NOW + timedelta(hours=1), ())

    short_tracker = ReplayOutcomeTracker("run-1")
    full_tracker = ReplayOutcomeTracker("run-1")
    short_tracker.push(execution_candle(0), signal)
    full_tracker.push(execution_candle(0), signal)
    short_result = short_tracker.push(execution_candle(1), no_trade)
    full_result = full_tracker.push(execution_candle(1), no_trade)
    full_tracker.push(execution_candle(2), no_trade)
    full_tracker.push(execution_candle(3), no_trade)

    assert short_result == full_result
