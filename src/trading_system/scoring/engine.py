"""Specification-defined location and confidence calculations."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import ROUND_HALF_EVEN, Decimal


def _bounded(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("score inputs must be finite")
    return min(max(value, Decimal(0)), Decimal(100))


@dataclass(frozen=True, slots=True)
class LocationComponents:
    distance_to_support_adr: Decimal
    runway_adr: Decimal | None
    adr_utilization: Decimal
    stop_distance_adr: Decimal


def location_score(components: LocationComponents) -> Decimal:
    support = Decimal(100) * min(
        max(Decimal(1) - components.distance_to_support_adr, Decimal(0)), Decimal(1)
    )
    runway = (
        Decimal(100)
        if components.runway_adr is None
        else Decimal(100) * min(max(components.runway_adr / Decimal(2), Decimal(0)), Decimal(1))
    )
    extension = Decimal(100) * min(
        max((Decimal("1.50") - components.adr_utilization), Decimal(0)), Decimal(1)
    )
    invalidation = Decimal(100) * min(
        max(Decimal(1) - components.stop_distance_adr, Decimal(0)), Decimal(1)
    )
    result = (
        Decimal("0.30") * support
        + Decimal("0.30") * runway
        + Decimal("0.20") * extension
        + Decimal("0.20") * invalidation
    )
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class ConfidenceComponents:
    pattern_quality: Decimal
    confirmation_score: Decimal
    trend_context: Decimal
    mtf_score: Decimal
    volume_score: Decimal
    location_score: Decimal
    runway_score: Decimal
    risk_score: Decimal
    data_quality_score: Decimal


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    raw_score: Decimal
    final_score: Decimal
    applied_caps: tuple[str, ...]


def confidence_score(
    components: ConfidenceComponents,
    *,
    insufficient_htf_warmup: bool = False,
    volume_unavailable: bool = False,
    trigger_pending: bool = False,
    opposing_zone_close: bool = False,
    data_quality_warning: bool = False,
    invalid_stop_or_runway: bool = False,
) -> ConfidenceResult:
    values = tuple(_bounded(getattr(components, item.name)) for item in fields(components))
    weights = tuple(
        Decimal(value)
        for value in ("0.18", "0.14", "0.12", "0.12", "0.10", "0.12", "0.10", "0.07", "0.05")
    )
    raw = sum((value * weight for value, weight in zip(values, weights, strict=True)), Decimal(0))
    raw = raw.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    caps: list[tuple[str, Decimal]] = []
    for active, name, cap in (
        (insufficient_htf_warmup, "INSUFFICIENT_HTF_WARMUP", Decimal(59)),
        (volume_unavailable, "VOLUME_UNAVAILABLE", Decimal(69)),
        (trigger_pending, "TRIGGER_PENDING", Decimal(69)),
        (opposing_zone_close, "OPPOSING_ZONE_TOO_CLOSE", Decimal(64)),
        (data_quality_warning, "DATA_QUALITY_WARNING", Decimal(49)),
        (invalid_stop_or_runway, "INVALID_STOP_OR_RUNWAY", Decimal(0)),
    ):
        if active:
            caps.append((name, cap))
    final = min((cap for _name, cap in caps), default=raw)
    final = min(final, raw)
    return ConfidenceResult(raw, final, tuple(name for name, _cap in caps))
