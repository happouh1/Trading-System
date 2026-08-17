"""Structural plan construction without execution assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

from trading_system.domain import Direction, Timeframe, TradePlan
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class PlanResult:
    plan: TradePlan | None
    rejection_reasons: tuple[str, ...]
    stop_distance_adr: Decimal
    reward_risk: Decimal | None


def build_trade_plan(
    *,
    symbol: str,
    timeframe: Timeframe,
    direction: Direction,
    created_at: datetime,
    planned_entry: Decimal,
    structural_anchor: Decimal,
    adr20: Decimal,
    runway_adr: Decimal | None,
    pattern_instance_id: str,
    stop_buffer_adr: Decimal = Decimal("0.10"),
    min_stop_adr: Decimal = Decimal("0.20"),
    max_stop_adr: Decimal = Decimal("1.25"),
    min_runway_adr: Decimal = Decimal("1.00"),
    min_reward_risk: Decimal = Decimal("1.50"),
) -> PlanResult:
    values = (planned_entry, structural_anchor, adr20)
    if any(value <= 0 or not value.is_finite() for value in values):
        raise ValueError("entry, anchor, and ADR20 must be finite and positive")
    if direction is Direction.NONE:
        raise ValueError("plan direction cannot be NONE")
    buffer = stop_buffer_adr * adr20
    stop = structural_anchor - buffer if direction is Direction.LONG else structural_anchor + buffer
    risk = abs(planned_entry - stop)
    stop_distance = risk / adr20
    reward_risk = runway_adr * adr20 / risk if runway_adr is not None and risk > 0 else None
    reasons: list[str] = []
    directionally_valid = (
        stop < planned_entry if direction is Direction.LONG else stop > planned_entry
    )
    if not directionally_valid:
        reasons.append("INVALID_STOP_DIRECTION")
    if stop_distance < min_stop_adr:
        reasons.append("STOP_TOO_TIGHT")
    if stop_distance > max_stop_adr:
        reasons.append("STOP_TOO_WIDE")
    if runway_adr is None or runway_adr < min_runway_adr:
        reasons.append("POOR_RUNWAY")
    if reward_risk is None or reward_risk < min_reward_risk:
        reasons.append("POOR_REWARD_RISK")
    if reasons:
        return PlanResult(None, tuple(reasons), stop_distance, reward_risk)
    identity = (
        symbol,
        timeframe,
        direction,
        created_at,
        planned_entry,
        stop,
        pattern_instance_id,
    )
    plan = TradePlan(
        plan_id=deterministic_id("trade_plan", identity),
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        created_at=created_at,
        planned_entry=planned_entry,
        initial_stop=stop,
        risk_per_unit=risk,
        runway_adr=runway_adr,
        reward_risk=reward_risk,
        pattern_instance_id=pattern_instance_id,
    )
    return PlanResult(plan, (), stop_distance, reward_risk)


def normalized_units(risk_budget_currency: Decimal, risk_per_unit: Decimal) -> Decimal:
    if risk_budget_currency <= 0 or risk_per_unit <= 0:
        raise ValueError("risk budget and unit risk must be positive")
    if not risk_budget_currency.is_finite() or not risk_per_unit.is_finite():
        raise ValueError("risk budget and unit risk must be finite")
    return (risk_budget_currency / risk_per_unit).to_integral_value(rounding=ROUND_FLOOR)
