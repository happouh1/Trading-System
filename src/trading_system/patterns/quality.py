"""Approved causal Phase 1D pattern-quality primitives."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from trading_system.domain import Direction

_HUNDRED = Decimal(100)
_CENT = Decimal("0.01")


def _unit(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("score input must be finite")
    return min(max(value, Decimal(0)), Decimal(1))


def _score(value: Decimal) -> Decimal:
    return (_HUNDRED * _unit(value)).quantize(_CENT, rounding=ROUND_HALF_EVEN)


def wick_quality(
    wick_fraction: Decimal,
    *,
    minimum: Decimal = Decimal("0.40"),
    full_quality: Decimal = Decimal("0.80"),
) -> Decimal:
    """Normalize qualifying sweep wick evidence onto [0, 100]."""
    if minimum < 0 or full_quality <= minimum:
        raise ValueError("wick-quality bounds are invalid")
    return _score((wick_fraction - minimum) / (full_quality - minimum))


def trap_quality(
    *,
    direction: Direction,
    failure_distance_adr: Decimal,
    failure_clv: Decimal,
    candidate_rvol: Decimal | None,
    maximum_excursion_adr: Decimal,
    follow_through_distance_adr: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return total, failure-close, participation, and follow-through scores."""
    if direction is Direction.NONE:
        raise ValueError("trap direction cannot be NONE")
    failure = _score((failure_distance_adr - Decimal("0.10")) / Decimal("0.20"))
    volume = Decimal(0)
    if candidate_rvol is not None:
        volume = _score((candidate_rvol - Decimal("1.20")) / Decimal("0.80"))
    excursion = _score((maximum_excursion_adr - Decimal("0.25")) / Decimal("0.50"))
    participation = max(volume, excursion)
    close_path = (
        _score((failure_clv - Decimal("0.65")) / Decimal("0.35"))
        if direction is Direction.LONG
        else _score((Decimal("0.35") - failure_clv) / Decimal("0.35"))
    )
    price_path = _score(follow_through_distance_adr / Decimal("0.25"))
    follow_through = max(close_path, price_path)
    total = (
        Decimal("0.40") * failure
        + Decimal("0.30") * participation
        + Decimal("0.30") * follow_through
    ).quantize(_CENT, rounding=ROUND_HALF_EVEN)
    return total, failure, participation, follow_through
