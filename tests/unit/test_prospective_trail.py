from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from tests.unit.test_prospective_entry import OPEN, D, bar
from trading_system.domain import Candle, Direction
from trading_system.execution_sim.prospective_trail import TrailEvidence, assess_trail
from trading_system.risk import DamageInputs, PositionState


def state() -> PositionState:
    return PositionState(Direction.LONG, D(100), D(98), D(98), D(2), D(100))


def evidence(*, damage: DamageInputs | None = None) -> TrailEvidence:
    return TrailEvidence(
        adr20=D(4), adr_known_at=OPEN, ema20=None, ema_known_at=None,
        confirmed_swing=None, swing_known_at=None, prior_bar_extreme=None,
        prior_extreme_known_at=None,
        damage_inputs=damage or DamageInputs(False, False, False, False, False),
        damage_known_at=bar().close_time,
    )


def assess(candle: Candle, supplied: TrailEvidence, *, as_of: datetime | None = None) -> None:
    assess_trail(
        trade_id="trade", symbol="MSFT", prior_state=state(),
        prior_state_known_at=OPEN, candle=candle, evidence=supplied,
        adjustment_factor=D(1), received_at=candle.close_time,
        as_of=as_of if as_of is not None else candle.close_time,
    )


def test_one_r_trail_is_monotonic_and_only_known_after_receipt() -> None:
    candle = replace(bar(), high=D(102), raw_high=D(102), candle_id="")
    result = assess_trail(
        trade_id="trade", symbol="MSFT", prior_state=state(),
        prior_state_known_at=OPEN, candle=candle, evidence=evidence(),
        adjustment_factor=D(1), received_at=candle.close_time,
        as_of=candle.close_time,
    )
    assert result.status == "TRAIL_UPDATED"
    assert result.prior_stop == D(98)
    assert result.next_state.current_stop == D("99.8")
    assert candle.low < result.next_state.current_stop  # Trail is for the following bar only.
    assert result.next_state.bars_held == 1
    assert result.event_time == result.known_at == candle.close_time
    assert not result.qualifying_completed_trade and not result.broker_write_performed
    assert result == assess_trail(
        trade_id="trade", symbol="MSFT", prior_state=state(),
        prior_state_known_at=OPEN, candle=candle, evidence=evidence(),
        adjustment_factor=D(1), received_at=candle.close_time,
        as_of=candle.close_time,
    )


def test_two_r_uses_known_ema_and_confirmed_swing() -> None:
    candle = replace(bar(), high=D(104), raw_high=D(104), candle_id="")
    supplied = replace(
        evidence(), ema20=D("103.5"), ema_known_at=candle.close_time,
        confirmed_swing=D("103.2"), swing_known_at=candle.close_time,
    )
    result = assess_trail(
        trade_id="trade", symbol="MSFT", prior_state=state(),
        prior_state_known_at=OPEN, candle=candle, evidence=supplied,
        adjustment_factor=D(1), received_at=candle.close_time,
        as_of=candle.close_time,
    )
    assert result.next_state.current_stop == D("103.1")
    assert result.status == "TRAIL_UPDATED"


def test_structural_damage_queues_exit_without_retroactive_fill() -> None:
    candle = bar()
    supplied = evidence(damage=DamageInputs(True, True, True, False, False))
    result = assess_trail(
        trade_id="trade", symbol="MSFT", prior_state=state(),
        prior_state_known_at=OPEN, candle=candle, evidence=supplied,
        adjustment_factor=D(1), received_at=candle.close_time,
        as_of=candle.close_time,
    )
    assert result.damage_score == D(70)
    assert result.status == "STRUCTURAL_DAMAGE_EXIT_QUEUED"
    assert result.next_state.exit_queued
    assert result.next_state.current_stop == D(98)
    assert result.event_time == candle.close_time


def test_future_or_stopped_evidence_rejected() -> None:
    candle = bar()
    with pytest.raises(ValueError, match="unavailable"):
        assess(candle, evidence(), as_of=OPEN)
    with pytest.raises(ValueError, match="unavailable"):
        assess(candle, replace(evidence(), adr_known_at=OPEN + timedelta(seconds=1)))
    with pytest.raises(ValueError, match="paired"):
        assess(candle, replace(evidence(), ema20=D(100)))
    with pytest.raises(ValueError, match="unavailable"):
        assess(candle, replace(
            evidence(), ema20=D(100),
            ema_known_at=candle.close_time + timedelta(seconds=1),
        ))
    with pytest.raises(ValueError, match="unavailable"):
        assess(replace(candle, low=D(97), raw_low=D(97), candle_id=""), evidence())
    with pytest.raises(ValueError, match="unavailable"):
        assess(candle, replace(evidence(), damage_known_at=OPEN))
    with pytest.raises(ValueError, match="unavailable"):
        assess_trail(
            trade_id="trade", symbol="MSFT",
            prior_state=replace(state(), bars_held=40), prior_state_known_at=OPEN,
            candle=candle, evidence=evidence(), adjustment_factor=D(1),
            received_at=candle.close_time, as_of=candle.close_time,
        )
