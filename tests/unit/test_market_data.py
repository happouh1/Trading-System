from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trading_system.domain import Timeframe
from trading_system.market_data import IngestionError, StaticSessionCalendar, aggregate, read_ohlcv

ROOT = Path(__file__).parents[2]
SESSION_DATE = date(2026, 1, 5)
OPEN = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
CLOSE = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)


def calendar() -> StaticSessionCalendar:
    return StaticSessionCalendar({SESSION_DATE: (OPEN, CLOSE)})


def test_strict_csv_ingestion_and_session_aggregation() -> None:
    candles = read_ohlcv(ROOT / "tests/fixtures/xnys_one_session.csv", calendar())
    assert len(candles) == 7
    assert all(item.raw_open is not None for item in candles)
    daily = aggregate(candles, Timeframe.DAY_1, calendar())
    assert len(daily) == 1
    assert (daily[0].open, daily[0].high, daily[0].low, daily[0].close) == (
        candles[0].open,
        candles[-1].high,
        candles[0].low,
        candles[-1].close,
    )
    four_hour = aggregate(candles, Timeframe.HOUR_4, calendar())
    assert len(four_hour) == 2
    assert four_hour[0].open_time == OPEN
    assert four_hour[0].close_time == datetime(2026, 1, 5, 18, 30, tzinfo=UTC)
    assert four_hour[1].close_time == CLOSE


def test_input_permutation_is_normalized_deterministically() -> None:
    candles = read_ohlcv(ROOT / "tests/fixtures/xnys_one_session.csv", calendar())
    reversed_result = aggregate(reversed(candles), Timeframe.DAY_1, calendar())
    ordered_result = aggregate(candles, Timeframe.DAY_1, calendar())
    reversed_json = [item.to_json() for item in reversed_result]
    ordered_json = [item.to_json() for item in ordered_result]
    assert reversed_json == ordered_json


def test_missing_interval_is_rejected_not_filled() -> None:
    candles = read_ohlcv(ROOT / "tests/fixtures/xnys_one_session.csv", calendar())
    with pytest.raises(IngestionError, match="missing"):
        aggregate(candles[:2] + candles[3:], Timeframe.DAY_1, calendar())


def test_parquet_matches_csv(tmp_path: Path) -> None:
    arrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    csv_path = ROOT / "tests/fixtures/xnys_one_session.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    target = tmp_path / "fixture.parquet"
    parquet.write_table(arrow.Table.from_pylist(rows), target)
    csv_candles = read_ohlcv(csv_path, calendar())
    parquet_candles = read_ohlcv(target, calendar())
    assert [item.to_json() for item in csv_candles] == [item.to_json() for item in parquet_candles]
