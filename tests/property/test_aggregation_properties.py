from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_system.domain import Candle, Timeframe
from trading_system.market_data import StaticSessionCalendar, aggregate


def test_aggregated_ohlc_invariants_across_seeded_paths() -> None:
    rng = random.Random(20260101)
    session = date(2026, 1, 5)
    session_open = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    session_close = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)
    calendar = StaticSessionCalendar({session: (session_open, session_close)})
    for path in range(25):
        candles: list[Candle] = []
        price = Decimal("100")
        start = session_open
        for index in range(7):
            duration = timedelta(minutes=30 if index == 6 else 60)
            change = Decimal(rng.randint(-100, 100)) / Decimal(100)
            close = max(Decimal("1"), price + change)
            high = max(price, close) + Decimal("0.50")
            low = min(price, close) - Decimal("0.50")
            candles.append(
                Candle(
                    "AAPL",
                    Timeframe.HOUR_1,
                    start,
                    start + duration,
                    session,
                    price,
                    high,
                    low,
                    close,
                    Decimal(1000 + index),
                    True,
                    Decimal(1),
                    "property",
                    f"sha256:path-{path}",
                    raw_open=price,
                    raw_high=high,
                    raw_low=low,
                    raw_close=close,
                    raw_volume=Decimal(1000 + index),
                )
            )
            price = close
            start += duration
        result = aggregate(candles, Timeframe.DAY_1, calendar)[0]
        assert result.high >= max(result.open, result.close)
        assert result.low <= min(result.open, result.close)
        assert result.volume == sum((item.volume for item in candles), Decimal(0))

