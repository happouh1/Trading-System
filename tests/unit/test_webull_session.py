from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from trading_system.market_data import StaticSessionCalendar
from trading_system.webull import core_session_status

OPEN = datetime(2026, 8, 27, 13, 30, tzinfo=UTC)
CLOSE = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)
NEXT_OPEN = datetime(2026, 8, 28, 13, 30, tzinfo=UTC)
CALENDAR = StaticSessionCalendar({
    date(2026, 8, 27): (OPEN, CLOSE),
    date(2026, 8, 28): (NEXT_OPEN, datetime(2026, 8, 28, 20, 0, tzinfo=UTC)),
})


def test_core_session_status_is_open_only_inside_completed_bounds() -> None:
    at_open = core_session_status(OPEN, CALENDAR)
    assert at_open.is_open
    assert at_open.session_open == OPEN
    assert at_open.session_close == CLOSE
    assert at_open.next_open is None

    at_close = core_session_status(CLOSE, CALENDAR)
    assert not at_close.is_open
    assert at_close.next_open == NEXT_OPEN


def test_core_session_status_finds_same_day_open_without_network() -> None:
    before_open = core_session_status(
        datetime(2026, 8, 27, 12, 0, tzinfo=UTC), CALENDAR
    )
    assert not before_open.is_open
    assert before_open.next_open == OPEN
    assert before_open.calendar_name == "XNYS"
    assert before_open.calendar_version == "fixture-v1"


def test_core_session_status_rejects_invalid_time_and_lookahead() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        core_session_status(datetime(2026, 8, 27, 13, 30), CALENDAR)
    with pytest.raises(ValueError, match="positive integer"):
        core_session_status(OPEN, CALENDAR, lookahead_days=0)
    with pytest.raises(ValueError, match="no eligible XNYS session"):
        core_session_status(
            datetime(2026, 8, 29, 12, 0, tzinfo=UTC), CALENDAR,
            lookahead_days=1,
        )
