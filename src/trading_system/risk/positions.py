"""Monotonic trails, structural damage, and conservative bar collisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_system.domain import Candle, Direction


@dataclass(frozen=True, slots=True)
class DamageInputs:
    swing_break: bool
    level_loss: bool
    ma_damage: bool
    impulse: bool
    follow_through: bool


def structural_damage(inputs: DamageInputs) -> Decimal:
    return (
        Decimal(30) * Decimal(int(inputs.swing_break))
        + Decimal(25) * Decimal(int(inputs.level_loss))
        + Decimal(15) * Decimal(int(inputs.ma_damage))
        + Decimal(15) * Decimal(int(inputs.impulse))
        + Decimal(15) * Decimal(int(inputs.follow_through))
    )


@dataclass(frozen=True, slots=True)
class PositionState:
    direction: Direction
    entry: Decimal
    initial_stop: Decimal
    current_stop: Decimal
    risk: Decimal
    favorable_extreme: Decimal
    bars_held: int = 0
    exit_queued: bool = False


def update_trail(
    state: PositionState,
    *,
    candle: Candle,
    adr20: Decimal,
    ema20: Decimal | None,
    confirmed_swing: Decimal | None,
    prior_bar_extreme: Decimal | None,
    damage_score: Decimal,
) -> PositionState:
    if state.direction is Direction.NONE:
        raise ValueError("position direction cannot be NONE")
    favorable = (
        max(state.favorable_extreme, candle.high)
        if state.direction is Direction.LONG
        else min(state.favorable_extreme, candle.low)
    )
    excursion = (
        (favorable - state.entry) / state.risk
        if state.direction is Direction.LONG
        else (state.entry - favorable) / state.risk
    )
    candidates = [state.current_stop]
    if excursion >= Decimal(1):
        candidates.append(
            state.entry - Decimal("0.10") * state.risk
            if state.direction is Direction.LONG
            else state.entry + Decimal("0.10") * state.risk
        )
    if excursion >= Decimal(2):
        if ema20 is not None:
            candidates.append(
                ema20 - Decimal("0.10") * adr20
                if state.direction is Direction.LONG
                else ema20 + Decimal("0.10") * adr20
            )
        if confirmed_swing is not None:
            candidates.append(
                confirmed_swing - Decimal("0.10") * adr20
                if state.direction is Direction.LONG
                else confirmed_swing + Decimal("0.10") * adr20
            )
    if Decimal(50) <= damage_score < Decimal(70) and prior_bar_extreme is not None:
        candidates.append(
            prior_bar_extreme - Decimal("0.10") * adr20
            if state.direction is Direction.LONG
            else prior_bar_extreme + Decimal("0.10") * adr20
        )
    stop = max(candidates) if state.direction is Direction.LONG else min(candidates)
    return PositionState(
        direction=state.direction,
        entry=state.entry,
        initial_stop=state.initial_stop,
        current_stop=stop,
        risk=state.risk,
        favorable_extreme=favorable,
        bars_held=state.bars_held + 1,
        exit_queued=state.exit_queued or damage_score >= Decimal(70),
    )


@dataclass(frozen=True, slots=True)
class BarExit:
    should_exit: bool
    reason: str | None
    price: Decimal | None


def resolve_bar_exit(
    state: PositionState,
    candle: Candle,
    *,
    target_price: Decimal | None = None,
    max_hold_bars: int = 40,
) -> BarExit:
    stop_hit = (
        candle.low <= state.current_stop
        if state.direction is Direction.LONG
        else candle.high >= state.current_stop
    )
    target_hit = target_price is not None and (
        candle.high >= target_price
        if state.direction is Direction.LONG
        else candle.low <= target_price
    )
    if stop_hit:
        return BarExit(True, "STOP_HIT_ADVERSE_FIRST" if target_hit else "STOP_HIT", state.current_stop)
    if target_hit:
        return BarExit(True, "TARGET_HIT", target_price)
    if state.bars_held >= max_hold_bars:
        return BarExit(True, "MAX_HOLD", candle.close)
    if state.exit_queued:
        return BarExit(False, "STRUCTURAL_DAMAGE_EXIT_QUEUED", None)
    return BarExit(False, None, None)
