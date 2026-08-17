from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_system.decisions import DecisionCandidate, DecisionEngine
from trading_system.domain import (
    DecisionAction,
    Direction,
    PatternEvent,
    PatternState,
    Timeframe,
    TradePlan,
)

D = Decimal
NOW = datetime(2026, 1, 5, 20, 0, tzinfo=UTC)


def candidate(
    direction: Direction = Direction.LONG,
    *,
    confidence: str = "80",
    trigger: bool = True,
    runway: str = "2",
) -> DecisionCandidate:
    event = PatternEvent(
        event_id=f"event-{direction.value}",
        run_id="run-1",
        observation_id="observation-1",
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        known_at=NOW,
        pattern_family="BREAKOUT" if direction is Direction.LONG else "BREAKDOWN",
        pattern_name="BASE_BREAK",
        pattern_version="1.0.0",
        instance_id=f"instance-{direction.value}",
        prior_state=PatternState.PENDING,
        new_state=PatternState.ACCEPTED,
        direction=direction,
        reference_level=D("100"),
    )
    stop = D("99") if direction is Direction.LONG else D("101")
    plan = TradePlan(
        plan_id=f"plan-{direction.value}",
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        direction=direction,
        created_at=NOW,
        planned_entry=D("100"),
        initial_stop=stop,
        risk_per_unit=D("1"),
        runway_adr=D(runway),
        reward_risk=D("2"),
        pattern_instance_id=event.instance_id,
    )
    return DecisionCandidate(
        event=event,
        setup_quality=D("85"),
        entry_quality=D("80"),
        confidence=D(confidence),
        mtf_score=D("70"),
        adr_utilization=D("0.7"),
        stop_distance_adr=D("0.5"),
        runway_adr=D(runway),
        reward_risk=D("2"),
        plan=plan,
        trigger_confirmed=trigger,
    )


def test_all_gates_pass_produces_directional_decision() -> None:
    decision = DecisionEngine("run-1").decide("observation-1", NOW, (candidate(),))
    assert decision.action is DecisionAction.LONG
    assert decision.entry_plan is not None
    assert all(rule.passed for rule in decision.explanation)


def test_pending_trigger_with_sufficient_confidence_produces_watch() -> None:
    decision = DecisionEngine("run-1").decide(
        "observation-1", NOW, (candidate(confidence="69", trigger=False),)
    )
    assert decision.action is DecisionAction.WATCH
    assert decision.missing_conditions == ("TRIGGER_PENDING", "LOW_CONFIDENCE")


def test_invalid_runway_is_explained_no_trade() -> None:
    decision = DecisionEngine("run-1").decide(
        "observation-1", NOW, (candidate(runway="0.5"),)
    )
    assert decision.action is DecisionAction.NO_TRADE
    assert "POOR_RUNWAY" in decision.rejection_reasons


def test_equal_priority_opposites_within_five_points_conflict() -> None:
    decision = DecisionEngine("run-1").decide(
        "observation-1",
        NOW,
        (candidate(Direction.LONG, confidence="80"), candidate(Direction.SHORT, confidence="77")),
    )
    assert decision.action is DecisionAction.NO_TRADE
    assert decision.rejection_reasons == ("CONFLICTING_SIGNALS",)
