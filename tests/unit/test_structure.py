from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from trading_system.domain import Candle, SwingKind, Timeframe
from trading_system.structure import StructureEngine, StructureState

D = Decimal


def candle(index: int, high: str, low: str) -> Candle:
    start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC) + timedelta(hours=index)
    midpoint = (D(high) + D(low)) / D("2")
    return Candle(
        symbol="AAPL",
        timeframe=Timeframe.HOUR_1,
        open_time=start,
        close_time=start + timedelta(hours=1),
        session_date=date(2026, 1, 5),
        open=midpoint,
        high=D(high),
        low=D(low),
        close=midpoint,
        volume=D("1000"),
        is_complete=True,
        adjustment_factor=D("1"),
        source="fixture",
        source_revision="sha256:structure-v1",
    )


def test_pivot_is_absent_until_right_window_closes() -> None:
    engine = StructureEngine(left=2, right=2)
    bars = [
        candle(0, "10", "8"),
        candle(1, "11", "8"),
        candle(2, "13", "9"),
        candle(3, "12", "8"),
        candle(4, "11", "7"),
    ]
    snapshots = [engine.push(item, D("2")) for item in bars]
    assert all(not snapshot.new_swings for snapshot in snapshots[:4])
    swing = snapshots[4].new_swings[0]
    assert swing.kind is SwingKind.HIGH
    assert swing.pivot_time == bars[2].close_time
    assert swing.confirmed_at == bars[4].close_time
    assert all(bars[index].close_time <= swing.confirmed_at for index in range(5))


def test_equal_high_tie_resolves_to_earliest_candidate() -> None:
    engine = StructureEngine(left=1, right=1)
    bars = [candle(0, "10", "8"), candle(1, "12", "9"), candle(2, "12", "8")]
    snapshots = [engine.push(item, D("2")) for item in bars]
    highs = [
        swing
        for snapshot in snapshots
        for swing in snapshot.new_swings
        if swing.kind is SwingKind.HIGH
    ]
    assert len(highs) == 1
    assert highs[0].pivot_time == bars[1].close_time
    assert snapshots[-1].state is StructureState.UNKNOWN


def test_future_bars_do_not_change_prior_snapshot() -> None:
    initial = [candle(0, "10", "8"), candle(1, "12", "9"), candle(2, "11", "8")]
    first = StructureEngine(left=1, right=1)
    before = [first.push(item, D("2")) for item in initial]
    second = StructureEngine(left=1, right=1)
    replayed = [second.push(item, D("2")) for item in initial]
    second.push(candle(3, "20", "7"), D("2"))
    assert replayed == before
