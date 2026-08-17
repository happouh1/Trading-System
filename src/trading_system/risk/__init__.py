"""Deterministic Phase 1C trade planning and normalized sizing."""

from trading_system.risk.plans import PlanResult, build_trade_plan, normalized_units
from trading_system.risk.positions import (
    BarExit,
    DamageInputs,
    PositionState,
    resolve_bar_exit,
    structural_damage,
    update_trail,
)

__all__ = [
    "BarExit",
    "DamageInputs",
    "PlanResult",
    "PositionState",
    "build_trade_plan",
    "normalized_units",
    "resolve_bar_exit",
    "structural_damage",
    "update_trail",
]
