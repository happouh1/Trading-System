from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tests.unit.test_break_patterns import pattern_bar, resistance

from trading_system.decisions import DecisionCandidate, DecisionEngine
from trading_system.domain import DecisionAction, Direction
from trading_system.execution_sim import execute_next_open, execute_queued_next_open_exit
from trading_system.patterns import BreakPatternMachine
from trading_system.persistence import RunRecord, SQLiteRepository
from trading_system.risk import (
    DamageInputs,
    PositionState,
    build_trade_plan,
    structural_damage,
    update_trail,
)

D = Decimal


def test_accepted_breakout_runs_through_decision_execution_and_persistence(
    tmp_path: Path,
) -> None:
    bars = [
        pattern_bar(0, "99.5", "100", "99", "100"),
        pattern_bar(1, "99.2", "101.2", "99", "101"),
        pattern_bar(2, "100", "100.6", "99.8", "100.4", retest=True),
        pattern_bar(3, "101", "104", "100.5", "103"),
        pattern_bar(4, "100", "101", "99", "100"),
    ]
    pattern_machine = BreakPatternMachine("run-1", "sha256:config", "git:test")
    level = resistance()
    pattern_machine.push(bars[0], (level,))
    pattern_machine.push(bars[1], (level,))
    accepted = pattern_machine.push(bars[2], (level,))[0]
    plan_result = build_trade_plan(
        symbol="AAPL",
        timeframe=bars[2].candle.timeframe,
        direction=Direction.LONG,
        created_at=bars[2].candle.close_time,
        planned_entry=D("101"),
        structural_anchor=D("99"),
        adr20=D("2"),
        runway_adr=D("2"),
        pattern_instance_id=accepted.instance_id,
    )
    assert plan_result.plan is not None
    candidate = DecisionCandidate(
        event=accepted,
        setup_quality=D("85"),
        entry_quality=D("80"),
        confidence=D("80"),
        mtf_score=D("70"),
        adr_utilization=D("0.7"),
        stop_distance_adr=plan_result.stop_distance_adr,
        runway_adr=D("2"),
        reward_risk=plan_result.reward_risk,
        plan=plan_result.plan,
        trigger_confirmed=True,
    )
    decision = DecisionEngine("run-1").decide(
        bars[2].observation.observation_id,
        bars[2].candle.close_time,
        (candidate,),
    )
    assert decision.action is DecisionAction.LONG
    entry = execute_next_open(
        run_id="run-1",
        trade_id="trade-1",
        plan=plan_result.plan,
        next_candle=bars[3].candle,
        atr20=D("2"),
        adr20=D("2"),
        quantity=D("10"),
    )
    assert entry.fill_price is not None
    position = PositionState(
        Direction.LONG,
        entry.fill_price,
        plan_result.plan.initial_stop,
        plan_result.plan.initial_stop,
        entry.fill_price - plan_result.plan.initial_stop,
        entry.fill_price,
    )
    damage = structural_damage(DamageInputs(True, True, True, False, False))
    position = update_trail(
        position,
        candle=bars[3].candle,
        adr20=D("2"),
        ema20=D("101"),
        confirmed_swing=D("100"),
        prior_bar_extreme=D("100"),
        damage_score=damage,
    )
    exit_result = execute_queued_next_open_exit(
        run_id="run-1",
        trade_id="trade-1",
        state=position,
        signal_candle=bars[3].candle,
        next_candle=bars[4].candle,
        atr20=D("2"),
        quantity=D("10"),
        reason="STRUCTURAL_DAMAGE",
    )
    database = tmp_path / "phase1c-flow.sqlite"
    run = RunRecord(
        "run-1",
        datetime(2026, 1, 1, tzinfo=UTC),
        "git:test",
        "sha256:config",
        "sha256:data",
        "fixture-v1",
        20260101,
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        for bar in bars:
            repository.insert_candle(bar.candle)
            repository.insert_snapshot(bar.observation)
        repository.insert_pattern_event(accepted)
        repository.insert_decision(decision)
        repository.insert_trade_event(entry.event)
        repository.insert_trade_event(exit_result.event)
        counts = repository.connection.execute(
            "SELECT (SELECT COUNT(*) FROM decisions), (SELECT COUNT(*) FROM trade_events)"
        ).fetchone()
        assert counts == (1, 2)
