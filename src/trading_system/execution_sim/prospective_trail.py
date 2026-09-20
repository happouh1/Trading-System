"""Causal offline trailing-stop assessment; never an executable broker action."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from trading_system.domain import Candle, Direction
from trading_system.execution_sim.prospective_max_hold import MAX_HOLD_BARS
from trading_system.risk import DamageInputs, PositionState, structural_damage, update_trail
from trading_system.serialization import deterministic_id

VERSION = "PROSPECTIVE_TRAIL.1.0"


def _utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamps required")


@dataclass(frozen=True, slots=True)
class TrailEvidence:
    adr20: Decimal
    adr_known_at: datetime
    ema20: Decimal | None
    ema_known_at: datetime | None
    confirmed_swing: Decimal | None
    swing_known_at: datetime | None
    prior_bar_extreme: Decimal | None
    prior_extreme_known_at: datetime | None
    damage_inputs: DamageInputs
    damage_known_at: datetime


@dataclass(frozen=True, slots=True)
class TrailAssessment:
    assessment_id: str
    trade_id: str
    symbol: str
    source_candle_id: str
    event_time: datetime
    known_at: datetime
    status: str
    damage_score: Decimal
    prior_stop: Decimal
    next_state: PositionState
    qualifying_completed_trade: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)


def assess_trail(
    *, trade_id: str, symbol: str, prior_state: PositionState,
    prior_state_known_at: datetime, candle: Candle, evidence: TrailEvidence,
    adjustment_factor: Decimal, received_at: datetime, as_of: datetime,
) -> TrailAssessment:
    """Evaluate only after the completed bar; updated stop applies to later bars."""
    for timestamp in (
        prior_state_known_at, evidence.adr_known_at, evidence.damage_known_at,
        received_at, as_of,
    ):
        _utc(timestamp)
    for price, known_at in (
        (evidence.ema20, evidence.ema_known_at),
        (evidence.confirmed_swing, evidence.swing_known_at),
        (evidence.prior_bar_extreme, evidence.prior_extreme_known_at),
    ):
        if (price is None) != (known_at is None):
            raise ValueError("optional trail values require paired knowledge timestamps")
        if known_at is not None:
            _utc(known_at)
        if price is not None and (not price.is_finite() or price <= 0):
            raise ValueError("invalid trail price")
    if (
        not trade_id or symbol == "AAPL" or candle.symbol != symbol
        or prior_state.direction is not Direction.LONG or not candle.is_complete
        or candle.adjustment_factor != adjustment_factor
        or not adjustment_factor.is_finite() or adjustment_factor <= 0
        or not evidence.adr20.is_finite() or evidence.adr20 <= 0
        or not prior_state.initial_stop.is_finite() or prior_state.initial_stop <= 0
        or not prior_state.current_stop.is_finite()
        or prior_state.current_stop < prior_state.initial_stop
        or not prior_state.entry.is_finite() or prior_state.entry <= prior_state.initial_stop
        or not prior_state.risk.is_finite() or prior_state.risk <= 0
        or prior_state.risk != prior_state.entry - prior_state.initial_stop
        or not prior_state.favorable_extreme.is_finite()
        or prior_state.favorable_extreme < prior_state.entry
        or prior_state.bars_held < 0 or prior_state.bars_held >= MAX_HOLD_BARS
        or prior_state.exit_queued
        or not all(isinstance(flag, bool) for flag in (
            evidence.damage_inputs.swing_break, evidence.damage_inputs.level_loss,
            evidence.damage_inputs.ma_damage, evidence.damage_inputs.impulse,
            evidence.damage_inputs.follow_through,
        ))
        or prior_state_known_at > candle.open_time
        or evidence.adr_known_at > candle.open_time
        or (evidence.prior_extreme_known_at is not None
            and evidence.prior_extreme_known_at > candle.open_time)
        or (evidence.ema_known_at is not None
            and evidence.ema_known_at > received_at)
        or (evidence.swing_known_at is not None
            and evidence.swing_known_at > received_at)
        or not candle.close_time <= evidence.damage_known_at <= received_at <= as_of
        or candle.low <= prior_state.current_stop
    ):
        raise ValueError("invalid, stopped, or unavailable trail evidence")
    damage_score = structural_damage(evidence.damage_inputs)
    next_state = update_trail(
        prior_state, candle=candle, adr20=evidence.adr20, ema20=evidence.ema20,
        confirmed_swing=evidence.confirmed_swing,
        prior_bar_extreme=evidence.prior_bar_extreme, damage_score=damage_score,
    )
    if next_state.current_stop < prior_state.current_stop:
        raise ValueError("long trailing stop cannot decrease")
    status = (
        "STRUCTURAL_DAMAGE_EXIT_QUEUED" if next_state.exit_queued else
        "TRAIL_UPDATED" if next_state.current_stop > prior_state.current_stop else
        "TRAIL_UNCHANGED"
    )
    identity = (
        VERSION, trade_id, symbol, prior_state, prior_state_known_at, candle,
        evidence, adjustment_factor, received_at, next_state, status,
    )
    return TrailAssessment(
        deterministic_id("sim_trail_assessment", identity), trade_id, symbol,
        candle.candle_id, candle.close_time, received_at, status, damage_score,
        prior_state.current_stop, next_state,
    )
