from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from tests.unit.test_prospective_entry import OPEN, D, bar
from trading_system.domain import Direction, PatternEvent, PatternState
from trading_system.execution_sim.prospective_opposing_trap import (
    OpposingTrapEvidence,
    OpposingTrapExitAssessment,
    assess_opposing_trap_exit,
    validate_opposing_trap_signal,
)

MIN_SCORE = Decimal(75)


def evidence(candle_id: str, at: datetime, *, confidence: str = "75") -> OpposingTrapEvidence:
    return OpposingTrapEvidence(
        PatternEvent(
            event_id="trap-1", run_id="run-1", observation_id="obs-1",
            symbol="MSFT", timeframe=bar().timeframe, known_at=at,
            pattern_family="BREAKOUT", pattern_name="TRAP", pattern_version="1.0.0",
            instance_id="instance-1", prior_state=PatternState.PENDING,
            new_state=PatternState.TRAP_CONFIRMED, direction=Direction.SHORT,
            reference_level=D(100), evidence_candle_ids=(candle_id,),
        ),
        D(confidence),
    )


def test_signal_is_current_completed_opposite_trap_with_threshold() -> None:
    candle = bar()
    valid = evidence(candle.candle_id, candle.close_time)
    validate_opposing_trap_signal(evidence=valid, candle=candle, received_at=candle.close_time)
    invalid = (
        replace(valid, confidence=D("74.99")),
        replace(valid, confidence=D("NaN")),
        replace(valid, event=replace(valid.event, direction=Direction.LONG)),
        replace(valid, event=replace(valid.event, new_state=PatternState.PENDING)),
        replace(valid, event=replace(valid.event, evidence_candle_ids=())),
        replace(
            valid, event=replace(
                valid.event, known_at=candle.close_time + timedelta(seconds=1),
            ),
        ),
    )
    for item in invalid:
        with pytest.raises(ValueError, match="opposing-trap signal"):
            validate_opposing_trap_signal(
                evidence=item, candle=candle, received_at=candle.close_time,
            )


def test_next_open_exit_requires_prior_signal_and_models_slippage() -> None:
    first = bar()
    second = replace(
        first, open_time=first.close_time,
        close_time=first.close_time + timedelta(hours=1),
        open=D(102), high=D(103), low=D(101), close=D(102),
        raw_open=D(102), raw_high=D(103), raw_low=D(101), raw_close=D(102),
        candle_id="",
    )
    def assess(
        *, signal_known_at: datetime = first.close_time,
        signal_confidence: Decimal = MIN_SCORE,
        as_of: datetime = second.close_time,
    ) -> OpposingTrapExitAssessment:
        return assess_opposing_trap_exit(
            trade_id="trade-1", symbol="MSFT", signal_candle_id=first.candle_id,
            signal_event_id="trap-1", signal_known_at=signal_known_at,
            signal_confidence=signal_confidence, candle=second, atr20=D(2),
            feature_known_at=OPEN, adjustment_factor=D(1),
            received_at=second.close_time, as_of=as_of,
        )

    result = assess()
    assert result.status == "OPPOSING_TRAP_EXIT_MODELLED"
    assert result.fill_price == D("101.96")
    assert result.event_time == second.open_time
    assert result.known_at == second.close_time
    assert not result.qualifying_completed_trade and not result.broker_write_performed
    assert result == assess()
    with pytest.raises(ValueError, match="opposing-trap exit evidence"):
        assess(signal_known_at=second.open_time + timedelta(seconds=1))
    with pytest.raises(ValueError, match="opposing-trap exit evidence"):
        assess(signal_confidence=D("74.99"))
    with pytest.raises(ValueError, match="opposing-trap exit evidence"):
        assess(as_of=first.close_time)
