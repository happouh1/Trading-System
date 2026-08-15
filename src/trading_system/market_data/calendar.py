"""Exchange-session boundaries used by validation and aggregation."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any, Protocol, cast


class SessionCalendar(Protocol):
    @property
    def name(self) -> str:
        """Stable exchange-calendar name."""
        ...

    @property
    def version(self) -> str:
        """Stable calendar data/version identifier."""
        ...

    def bounds(self, session_date: date) -> tuple[datetime, datetime] | None:
        """Return the completed regular-session UTC bounds, or None for a closed date."""
        ...


@dataclass(frozen=True, slots=True)
class StaticSessionCalendar:
    """Deterministic test/research calendar with explicitly supplied sessions."""

    sessions: Mapping[date, tuple[datetime, datetime]]
    name: str = "XNYS"
    version: str = "fixture-v1"

    def __post_init__(self) -> None:
        checked: dict[date, tuple[datetime, datetime]] = {}
        for session_date, (open_time, close_time) in self.sessions.items():
            if open_time.tzinfo is None or close_time.tzinfo is None:
                raise ValueError("session bounds must be timezone-aware")
            if close_time <= open_time:
                raise ValueError("session close must follow open")
            checked[session_date] = (open_time.astimezone(UTC), close_time.astimezone(UTC))
        object.__setattr__(self, "sessions", MappingProxyType(checked))

    def bounds(self, session_date: date) -> tuple[datetime, datetime] | None:
        return self.sessions.get(session_date)


class XNYSCalendar:
    """Authoritative XNYS regular-session adapter backed by exchange-calendars."""

    name = "XNYS"
    version = "exchange-calendars-4"

    def __init__(self) -> None:
        module = importlib.import_module("exchange_calendars")
        self._calendar: Any = module.get_calendar("XNYS")

    def bounds(self, session_date: date) -> tuple[datetime, datetime] | None:
        pandas = importlib.import_module("pandas")
        label = pandas.Timestamp(session_date.isoformat())
        if not bool(self._calendar.is_session(label)):
            return None
        open_value = self._calendar.session_open(label).to_pydatetime()
        close_value = self._calendar.session_close(label).to_pydatetime()
        session_open = cast(datetime, open_value).astimezone(UTC)
        session_close = cast(datetime, close_value).astimezone(UTC)
        return session_open, session_close
