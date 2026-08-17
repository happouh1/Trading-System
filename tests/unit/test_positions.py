from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from tests.unit.test_features import daily_candle

from trading_system.domain import Direction
from trading_system.risk import (
    DamageInputs,
    PositionState,
    resolve_bar_exit,
    structural_damage,
    update_trail,
)

D = Decimal


def position() -> PositionState:
    return PositionState(Direction.LONG, D("100"), D("98"), D("98"), D("2"), D("100"))


def test_long_trail_never_decreases() -> None:
    state = position()
    first = update_trail(
        state,
        candle=replace(daily_candle(0), high=D("103"), candle_id=""),
        adr20=D("4"),
        ema20=D("100"),
        confirmed_swing=D("99"),
        prior_bar_extreme=D("99"),
        damage_score=D("0"),
    )
    second = update_trail(
        first,
        candle=replace(daily_candle(1), high=D("105"), candle_id=""),
        adr20=D("4"),
        ema20=D("101"),
        confirmed_swing=D("100"),
        prior_bar_extreme=D("100"),
        damage_score=D("55"),
    )
    assert first.current_stop >= state.current_stop
    assert second.current_stop >= first.current_stop


def test_damage_score_queues_exit_at_seventy() -> None:
    score = structural_damage(DamageInputs(True, True, True, False, False))
    assert score == D("70")
    updated = update_trail(
        position(),
        candle=daily_candle(0),
        adr20=D("4"),
        ema20=None,
        confirmed_swing=None,
        prior_bar_extreme=None,
        damage_score=score,
    )
    assert updated.exit_queued


def test_stop_wins_ambiguous_stop_target_bar() -> None:
    candle = replace(daily_candle(0), high=D("104"), low=D("97"), candle_id="")
    result = resolve_bar_exit(position(), candle, target_price=D("104"))
    assert result.should_exit
    assert result.reason == "STOP_HIT_ADVERSE_FIRST"
    assert result.price == D("98")
