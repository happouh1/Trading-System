"""Deterministic regular-session safety gates for Webull operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from trading_system.market_data.calendar import SessionCalendar


@dataclass(frozen=True, slots=True)
class CoreSessionStatus:
    """Causal XNYS regular-session status evaluated at one instant."""

    evaluated_at: datetime
    calendar_name: str
    calendar_version: str
    is_open: bool
    session_open: datetime | None
    session_close: datetime | None
    next_open: datetime | None

    def __post_init__(self) -> None:
        values = (
            self.evaluated_at,
            self.session_open,
            self.session_close,
            self.next_open,
        )
        if any(
            value is not None and (value.tzinfo is None or value.utcoffset() is None)
            for value in values
        ):
            raise ValueError("Webull session timestamps must be timezone-aware")
        if not self.calendar_name or not self.calendar_version:
            raise ValueError("Webull session calendar identity is required")
        if self.is_open:
            if self.session_open is None or self.session_close is None:
                raise ValueError("open Webull session status requires session bounds")
            if not self.session_open <= self.evaluated_at < self.session_close:
                raise ValueError("open Webull session status is outside its bounds")
            if self.next_open is not None:
                raise ValueError("open Webull session status cannot have a next open")
        elif self.next_open is None or self.next_open <= self.evaluated_at:
            raise ValueError("closed Webull session status requires a future next open")


def core_session_status(
    evaluated_at: datetime,
    calendar: SessionCalendar,
    *,
    lookahead_days: int = 15,
) -> CoreSessionStatus:
    """Return regular-session status without consulting a broker or wall-clock future."""

    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("Webull session evaluation time must be timezone-aware")
    if isinstance(lookahead_days, bool) or lookahead_days <= 0:
        raise ValueError("Webull session lookahead must be a positive integer")
    evaluated_at = evaluated_at.astimezone(UTC)
    bounds = calendar.bounds(evaluated_at.date())
    if bounds is not None and bounds[0] <= evaluated_at < bounds[1]:
        return CoreSessionStatus(
            evaluated_at,
            calendar.name,
            calendar.version,
            True,
            bounds[0],
            bounds[1],
            None,
        )
    for offset in range(lookahead_days):
        candidate = calendar.bounds((evaluated_at + timedelta(days=offset)).date())
        if candidate is not None and candidate[0] > evaluated_at:
            return CoreSessionStatus(
                evaluated_at,
                calendar.name,
                calendar.version,
                False,
                bounds[0] if bounds is not None else None,
                bounds[1] if bounds is not None else None,
                candidate[0],
            )
    raise ValueError(
        f"no eligible {calendar.name} session open found within {lookahead_days} days"
    )
