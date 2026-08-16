from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_system.domain import (
    Candle,
    Level,
    LevelKind,
    Observation,
    PatternState,
    Timeframe,
)
from trading_system.patterns import (
    BreakPatternMachine,
    PatternBar,
    ReclaimPatternMachine,
    SweepPatternMachine,
)

D = Decimal
START = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def pattern_bar(
    index: int,
    open_price: str,
    high: str,
    low: str,
    close: str,
    *,
    rvol: str = "2",
    retest: bool = False,
) -> PatternBar:
    candle = Candle(
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        open_time=START + timedelta(hours=index),
        close_time=START + timedelta(hours=index + 1),
        session_date=date(2026, 1, 5),
        open=D(open_price),
        high=D(high),
        low=D(low),
        close=D(close),
        volume=D("1000"),
        is_complete=True,
        adjustment_factor=D("1"),
        source="fixture",
        source_revision="sha256:patterns-v1",
    )
    candle_range = candle.high - candle.low
    body = abs(candle.close - candle.open)
    observation = Observation(
        observation_id=f"observation-{index}",
        run_id="run-1",
        candle_id=candle.candle_id,
        known_at=candle.close_time,
        schema_version="1.0.0",
        input_fingerprint=f"fingerprint-{index}",
        features={
            "range": candle_range,
            "body": body,
            "clv": (candle.close - candle.low) / candle_range,
            "lower_wick": min(candle.open, candle.close) - candle.low,
            "upper_wick": candle.high - max(candle.open, candle.close),
            "rvol20": D(rvol),
        },
        data_quality={"complete": True},
    )
    return PatternBar(candle, observation, D("2"), D("2"), retest)


def resistance() -> Level:
    return Level(
        level_id="level-1",
        run_id="run-1",
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        known_at=START - timedelta(hours=1),
        lower_price=D("100"),
        upper_price=D("100"),
        kind=LevelKind.BASE_BOUNDARY,
        confluence_score=D("50"),
        evidence_candle_ids=("source-candle",),
    )


def test_breakout_candidate_becomes_pending_then_accepted_causally() -> None:
    machine = BreakPatternMachine("run-1", "sha256:config", "git:test")
    level = resistance()
    assert machine.push(pattern_bar(0, "99.5", "100", "99", "100"), (level,)) == ()
    candidate = machine.push(pattern_bar(1, "99.2", "101.2", "99", "101"), (level,))
    assert len(candidate) == 1
    assert candidate[0].new_state is PatternState.CANDIDATE
    accepted = machine.push(
        pattern_bar(2, "100", "100.6", "99.8", "100.4", retest=True), (level,)
    )
    assert len(accepted) == 1
    assert accepted[0].prior_state is PatternState.CANDIDATE
    assert accepted[0].new_state is PatternState.ACCEPTED
    assert accepted[0].known_at == START + timedelta(hours=3)


def test_future_bar_does_not_retroactively_stamp_acceptance() -> None:
    machine = BreakPatternMachine("run-1", "sha256:config", "git:test")
    level = resistance()
    machine.push(pattern_bar(0, "99.5", "100", "99", "100"), (level,))
    candidate = machine.push(pattern_bar(1, "99.2", "101.2", "99", "101"), (level,))[0]
    machine.push(pattern_bar(2, "100", "100.6", "99.8", "100.4", retest=True), (level,))
    assert candidate.new_state is PatternState.CANDIDATE
    assert candidate.known_at == START + timedelta(hours=2)


def test_bullish_sweep_waits_for_two_closed_confirmation_bars() -> None:
    machine = SweepPatternMachine("run-1", "sha256:config", "git:test")
    level = resistance()
    candidate = machine.push(pattern_bar(0, "100", "101", "99.2", "100.8"), (level,))
    assert candidate[0].new_state is PatternState.CANDIDATE
    pending = machine.push(pattern_bar(1, "100.2", "101", "100", "100.7"), (level,))
    assert pending[0].new_state is PatternState.PENDING
    confirmed = machine.push(pattern_bar(2, "100.2", "100.8", "100", "100.5"), (level,))
    assert confirmed[0].new_state is PatternState.ACCEPTED
    assert confirmed[0].reason_codes == ("SWEEP_REVERSAL_CONFIRMED",)
    assert confirmed[0].known_at == START + timedelta(hours=3)


def test_reclaim_accepts_and_preserves_sweep_parent_link() -> None:
    machine = ReclaimPatternMachine("run-1", "sha256:config", "git:test")
    level = resistance()
    assert machine.push(pattern_bar(0, "99.5", "100", "98.5", "99"), (level,)) == ()
    candidate = machine.push(
        pattern_bar(1, "99.8", "101", "99.2", "100.8"),
        (level,),
        {level.level_id: "sweep-parent"},
    )[0]
    assert candidate.new_state is PatternState.CANDIDATE
    assert candidate.features["parent_instance_id"] == "sweep-parent"
    accepted = machine.push(
        pattern_bar(2, "100.1", "100.8", "99.9", "100.6", retest=True), (level,)
    )[0]
    assert accepted.new_state is PatternState.ACCEPTED
    assert accepted.reason_codes == ("RECLAIM_ACCEPTED",)


def test_reclaim_failure_is_known_only_on_failure_close() -> None:
    machine = ReclaimPatternMachine("run-1", "sha256:config", "git:test")
    level = resistance()
    machine.push(pattern_bar(0, "99.5", "100", "98.5", "99"), (level,))
    candidate = machine.push(pattern_bar(1, "99.8", "101", "99.2", "100.8"), (level,))[0]
    failed = machine.push(pattern_bar(2, "99.8", "100", "99", "99.5"), (level,))[0]
    assert failed.new_state is PatternState.FAILED
    assert failed.known_at > candidate.known_at
