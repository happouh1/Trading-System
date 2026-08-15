from __future__ import annotations

from datetime import UTC, date, datetime

from trading_system.market_data.calendar import XNYSCalendar


def test_authoritative_xnys_holiday_and_early_close() -> None:
    calendar = XNYSCalendar()
    assert calendar.bounds(date(2024, 7, 4)) is None
    assert calendar.bounds(date(2024, 11, 29)) == (
        datetime(2024, 11, 29, 14, 30, tzinfo=UTC),
        datetime(2024, 11, 29, 18, 0, tzinfo=UTC),
    )
