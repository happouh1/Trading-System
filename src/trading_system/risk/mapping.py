"""Approved causal trade-mapping primitives that do not require unresolved scores."""

from __future__ import annotations

from decimal import Decimal

from trading_system.domain import Direction, PatternEvent, PatternState


def structural_anchor(event: PatternEvent) -> Decimal | None:
    """Select the approved structural anchor from immutable event evidence."""
    sequence = event.features.get("sequence_extreme")
    retest = event.features.get("retest_extreme")
    if event.pattern_family in {"BREAKOUT", "BREAKDOWN"} and (
        event.new_state is PatternState.ACCEPTED
    ):
        reference = event.reference_level
        if reference is None:
            return None
        if not isinstance(retest, Decimal):
            return reference
        return (
            min(reference, retest)
            if event.direction is Direction.LONG
            else max(reference, retest)
        )
    if event.pattern_family in {"RECLAIM", "LIQUIDITY_SWEEP"} or (
        event.new_state is PatternState.TRAP_CONFIRMED
    ):
        return sequence if isinstance(sequence, Decimal) else None
    return None


def adr_utilization(
    session_open: Decimal,
    confirmation_close: Decimal,
    prior_adr20: Decimal,
) -> Decimal:
    """Absolute regular-session move known at confirmation, normalized by prior ADR."""
    if min(session_open, confirmation_close, prior_adr20) <= 0:
        raise ValueError("session prices and prior ADR20 must be positive")
    if not all(value.is_finite() for value in (session_open, confirmation_close, prior_adr20)):
        raise ValueError("ADR utilization inputs must be finite")
    return abs(confirmation_close - session_open) / prior_adr20
