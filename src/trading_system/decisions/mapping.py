"""Approved deterministic mapping from causal pattern evidence to decision candidates."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from trading_system.decisions.engine import DecisionCandidate
from trading_system.domain import Candle, Direction, Level, Observation, PatternEvent, PatternState
from trading_system.risk import adr_utilization, build_trade_plan, structural_anchor
from trading_system.scoring import (
    ConfidenceComponents,
    LocationComponents,
    MtfSnapshot,
    confidence_score,
    location_score,
    ma_slope_component,
    mtf_score,
)
from trading_system.structure import StructureState


def _decimal(features: object) -> Decimal | None:
    return features if isinstance(features, Decimal) else None


def _trend_score(
    candle: Candle,
    observation: Observation,
    structure: StructureState,
) -> Decimal | None:
    ema10 = _decimal(observation.features.get("ema10"))
    ema20 = _decimal(observation.features.get("ema20"))
    ema50 = _decimal(observation.features.get("ema50"))
    sma200 = _decimal(observation.features.get("sma200"))
    slope20 = _decimal(observation.features.get("ema20_slope_adr"))
    slope50 = _decimal(observation.features.get("ema50_slope_adr"))
    if None in (ema10, ema20, ema50, sma200, slope20, slope50):
        return None
    assert ema10 is not None
    assert ema20 is not None
    assert ema50 is not None
    assert sma200 is not None
    assert slope20 is not None
    assert slope50 is not None
    structure_value = {
        StructureState.UPTREND: Decimal(1),
        StructureState.DOWNTREND: Decimal(-1),
    }.get(structure, Decimal(0))
    ma_order = (
        Decimal(1)
        if ema10 > ema20 > ema50
        else Decimal(-1)
        if ema10 < ema20 < ema50
        else Decimal(0)
    )
    price_position = (
        Decimal(1)
        if candle.close > ema20 and candle.close > sma200
        else Decimal(-1)
        if candle.close < ema20 and candle.close < sma200
        else Decimal(0)
    )
    raw = (
        Decimal("0.40") * structure_value
        + Decimal("0.25") * ma_order
        + Decimal("0.20") * ma_slope_component(slope20, slope50)
        + Decimal("0.15") * price_position
    )
    return (Decimal(50) + Decimal(50) * raw).quantize(
        Decimal(1), rounding=ROUND_HALF_EVEN
    )


def _same_side_distance(
    entry: Decimal,
    direction: Direction,
    levels: tuple[Level, ...],
    adr20: Decimal,
) -> tuple[Decimal, bool]:
    if direction is Direction.LONG:
        distances = [entry - level.upper_price for level in levels if level.upper_price < entry]
    else:
        distances = [level.lower_price - entry for level in levels if level.lower_price > entry]
    return (min(distances) / adr20, False) if distances else (Decimal(1), True)


def map_pattern_candidate(
    *,
    event: PatternEvent,
    candle: Candle,
    observation: Observation,
    structure: StructureState,
    mtf: MtfSnapshot,
    levels: tuple[Level, ...],
    session_open: Decimal,
    position_already_open: bool = False,
) -> DecisionCandidate | None:
    """Map promotable pattern states; preserve incomplete evidence as an invalid candidate."""
    promotable = event.new_state in {PatternState.ACCEPTED, PatternState.TRAP_CONFIRMED}
    if not promotable or event.direction is Direction.NONE:
        return None
    adr20 = _decimal(observation.features.get("adr20"))
    atr20 = _decimal(observation.features.get("atr20"))
    pattern_quality = _decimal(event.features.get("pattern_quality"))
    confirmation = _decimal(event.features.get("confirmation_score"))
    trend = _trend_score(candle, observation, structure)
    anchor = structural_anchor(event)
    runway = _decimal(event.features.get("directional_runway_adr"))
    runway_present = "directional_runway_adr" in event.features
    critical = all(
        value is not None
        for value in (atr20, adr20, pattern_quality, confirmation, trend, anchor)
    ) and structure is not StructureState.UNKNOWN and runway_present and len(mtf.states) == 4
    plan_result = None
    stop_distance = None
    reward_risk = None
    if adr20 is not None and anchor is not None:
        plan_result = build_trade_plan(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            direction=event.direction,
            created_at=candle.close_time,
            planned_entry=candle.close,
            structural_anchor=anchor,
            adr20=adr20,
            runway_adr=runway,
            pattern_instance_id=event.instance_id,
        )
        stop_distance = plan_result.stop_distance_adr
        reward_risk = plan_result.reward_risk
    plan = plan_result.plan if plan_result is not None else None
    if plan is None:
        critical = False
    mtf_value = mtf_score(mtf, event.direction)
    utilization = (
        adr_utilization(session_open, candle.close, adr20)
        if adr20 is not None
        else Decimal(0)
    )
    if adr20 is not None and stop_distance is not None:
        same_side_distance, same_side_missing = _same_side_distance(
            candle.close, event.direction, levels, adr20
        )
        location = location_score(
            LocationComponents(
                same_side_distance,
                runway,
                utilization,
                stop_distance,
            )
        )
        risk_score = Decimal(100) * min(
            max((Decimal("1.25") - stop_distance) / Decimal("1.05"), Decimal(0)),
            Decimal(1),
        )
    else:
        same_side_missing = False
        location = Decimal(0)
        risk_score = Decimal(0)
    rvol = _decimal(observation.features.get("rvol20"))
    volume_score = (
        Decimal(50)
        if rvol is None
        else Decimal(100) * min(max(rvol / Decimal(2), Decimal(0)), Decimal(1))
    )
    runway_score = (
        Decimal(100)
        if runway is None
        else Decimal(100) * min(max(runway / Decimal(2), Decimal(0)), Decimal(1))
    )
    directional_trend = (
        trend
        if event.direction is Direction.LONG and trend is not None
        else Decimal(100) - trend
        if trend is not None
        else Decimal(0)
    )
    confidence = confidence_score(
        ConfidenceComponents(
            pattern_quality or Decimal(0),
            confirmation or Decimal(0),
            directional_trend,
            mtf_value,
            volume_score,
            location,
            runway_score,
            risk_score,
            Decimal(100) if critical else Decimal(0),
        ),
        insufficient_htf_warmup=len(mtf.states) < 4,
        volume_unavailable=rvol is None,
        invalid_stop_or_runway=plan is None,
        directly_opposed_higher_timeframes=_directly_opposed(mtf, event.direction),
    )
    setup = (
        Decimal("0.50") * (pattern_quality or Decimal(0))
        + Decimal("0.25") * directional_trend
        + Decimal("0.25") * mtf_value
    ).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    entry = (
        Decimal("0.40") * (confirmation or Decimal(0))
        + Decimal("0.40") * location
        + Decimal("0.20") * risk_score
    ).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    return DecisionCandidate(
        event=event,
        setup_quality=setup,
        entry_quality=entry,
        confidence=confidence.final_score,
        mtf_score=mtf_value,
        adr_utilization=utilization,
        stop_distance_adr=stop_distance,
        runway_adr=runway,
        reward_risk=reward_risk,
        plan=plan,
        trigger_confirmed=True,
        critical_features_complete=critical,
        position_already_open=position_already_open,
        timeframe_states=tuple(
            (state.timeframe.value, state.state.value) for state in mtf.states
        ),
        atr20=atr20,
        adr20=adr20,
        disclosures=("NO_CAUSAL_SAME_SIDE_ZONE",) if same_side_missing else (),
    )


def _directly_opposed(mtf: MtfSnapshot, direction: Direction) -> bool:
    strategic = {
        state.timeframe: state.state
        for state in mtf.states
        if state.timeframe.value in {"1w", "1d"}
    }
    opposed = (
        StructureState.DOWNTREND
        if direction is Direction.LONG
        else StructureState.UPTREND
    )
    return len(strategic) == 2 and all(state is opposed for state in strategic.values())
