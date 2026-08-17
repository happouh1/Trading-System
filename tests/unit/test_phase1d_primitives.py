from __future__ import annotations

from decimal import Decimal

from trading_system.domain import Direction
from trading_system.scoring import ma_slope_component, trap_quality, wick_quality

D = Decimal


def test_ma_slope_component_uses_approved_scale_and_caps() -> None:
    assert ma_slope_component(D("0.005"), D("0.005")) == D("0.5")
    assert ma_slope_component(D("0.02"), D("0.02")) == D("1")
    assert ma_slope_component(D("-0.02"), D("-0.02")) == D("-1")


def test_wick_quality_boundaries_and_midpoint() -> None:
    assert wick_quality(D("0.40")) == D("0.00")
    assert wick_quality(D("0.60")) == D("50.00")
    assert wick_quality(D("0.80")) == D("100.00")
    assert wick_quality(D("0.95")) == D("100.00")


def test_trap_quality_is_directionally_symmetric() -> None:
    bullish = trap_quality(
        direction=Direction.LONG,
        failure_distance_adr=D("0.20"),
        failure_clv=D("0.825"),
        candidate_rvol=D("1.60"),
        maximum_excursion_adr=D("0.50"),
        follow_through_distance_adr=D("0.125"),
    )
    bearish = trap_quality(
        direction=Direction.SHORT,
        failure_distance_adr=D("0.20"),
        failure_clv=D("0.175"),
        candidate_rvol=D("1.60"),
        maximum_excursion_adr=D("0.50"),
        follow_through_distance_adr=D("0.125"),
    )
    assert bullish == bearish
    assert bullish == (D("50.00"), D("50.00"), D("50.00"), D("50.00"))


def test_missing_rvol_uses_excursion_participation_only() -> None:
    result = trap_quality(
        direction=Direction.SHORT,
        failure_distance_adr=D("0.10"),
        failure_clv=D("0.35"),
        candidate_rvol=None,
        maximum_excursion_adr=D("0.50"),
        follow_through_distance_adr=D("0"),
    )
    assert result[2] == D("50.00")
