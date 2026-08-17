from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from tests.unit.test_decisions import candidate
from trading_system.domain import Direction, Timeframe
from trading_system.risk import (
    adr_utilization,
    build_trade_plan,
    normalized_units,
    structural_anchor,
)

D = Decimal
NOW = datetime(2026, 1, 5, 20, 0, tzinfo=UTC)


def test_long_plan_uses_anchor_minus_adr_buffer() -> None:
    result = build_trade_plan(
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        direction=Direction.LONG,
        created_at=NOW,
        planned_entry=D("102"),
        structural_anchor=D("100"),
        adr20=D("4"),
        runway_adr=D("2"),
        pattern_instance_id="pattern-1",
    )
    assert result.plan is not None
    assert result.plan.initial_stop == D("99.60")
    assert result.plan.risk_per_unit == D("2.40")
    assert result.reward_risk == D("3.333333333333333333333333333")


def test_invalid_stop_is_rejected_not_arbitrarily_tightened() -> None:
    result = build_trade_plan(
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        direction=Direction.LONG,
        created_at=NOW,
        planned_entry=D("100"),
        structural_anchor=D("100.5"),
        adr20=D("4"),
        runway_adr=D("2"),
        pattern_instance_id="pattern-1",
    )
    assert result.plan is None
    assert "STOP_TOO_TIGHT" in result.rejection_reasons


def test_normalized_sizing_rounds_down() -> None:
    assert normalized_units(D("1000"), D("3")) == D("333")


def test_break_anchor_uses_lower_retest_for_long() -> None:
    event = replace(
        candidate().event,
        features={"retest_extreme": D("99.5"), "sequence_extreme": D("99")},
    )
    assert structural_anchor(event) == D("99.5")


def test_adr_utilization_uses_confirmation_close_only() -> None:
    assert adr_utilization(D("100"), D("103"), D("4")) == D("0.75")


def test_null_runway_is_disclosed_not_rejected_or_invented() -> None:
    result = build_trade_plan(
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        direction=Direction.LONG,
        created_at=NOW,
        planned_entry=D("102"),
        structural_anchor=D("100"),
        adr20=D("4"),
        runway_adr=None,
        pattern_instance_id="pattern-no-opposition",
    )
    assert result.plan is not None
    assert result.plan.runway_adr is None
    assert result.plan.reward_risk is None
    assert result.disclosures == (
        "NO_CAUSAL_OPPOSING_ZONE",
        "REWARD_RISK_NOT_APPLICABLE_NO_OPPOSITION",
    )
    assert "POOR_RUNWAY" not in result.rejection_reasons
    assert "POOR_REWARD_RISK" not in result.rejection_reasons
