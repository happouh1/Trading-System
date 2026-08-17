from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import Candle, Observation, Timeframe
from trading_system.features import CausalFeatureEngine

ROOT = Path(__file__).parents[2]
D = Decimal


def daily_candle(index: int) -> Candle:
    session = date(2026, 1, 1) + timedelta(days=index)
    midnight = datetime.combine(session, datetime.min.time(), tzinfo=UTC)
    open_time = midnight + timedelta(hours=14, minutes=30)
    return Candle(
        symbol="AAPL",
        timeframe=Timeframe.DAY_1,
        open_time=open_time,
        close_time=open_time + timedelta(hours=6, minutes=30),
        session_date=session,
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100"),
        volume=D("1000"),
        is_complete=True,
        adjustment_factor=D("1"),
        source="fixture",
        source_revision="sha256:features-v1",
        raw_open=D("100"),
        raw_high=D("101"),
        raw_low=D("99"),
        raw_close=D("100"),
        raw_volume=D("1000"),
    )


def test_full_window_warmups_and_golden_snapshot() -> None:
    engine = CausalFeatureEngine("run-1")
    snapshots = [engine.push(daily_candle(index)) for index in range(21)]
    assert snapshots[8].features["ema10"] is None
    assert snapshots[9].features["ema10"] == D("100")
    assert snapshots[18].features["atr20"] is None
    assert snapshots[19].features["atr20"] == D("2")
    assert snapshots[19].features["adr20"] is None
    expected = json.loads((ROOT / "tests/golden/feature_snapshot_v1.json").read_text())
    actual = snapshots[20].features
    for name in ("atr20", "adr20", "rvol20", "ema10", "ema20"):
        actual_value = actual[name]
        expected_value = expected[name]
        assert isinstance(actual_value, Decimal)
        assert isinstance(expected_value, str)
        assert actual_value == D(expected_value)
    assert actual["ema50"] is expected["ema50"]
    assert actual["sma200"] is expected["sma200"]


def test_sma_and_long_ema_require_complete_windows() -> None:
    engine = CausalFeatureEngine("run-2")
    snapshots = [engine.push(daily_candle(index)) for index in range(200)]
    assert snapshots[48].features["ema50"] is None
    assert snapshots[49].features["ema50"] == D("100")
    assert snapshots[198].features["sma200"] is None
    assert snapshots[199].features["sma200"] == D("100")


def test_future_candles_do_not_change_prior_snapshots() -> None:
    first_engine = CausalFeatureEngine("same-run")
    prior = [first_engine.push(daily_candle(index)).to_json() for index in range(10)]
    second_engine = CausalFeatureEngine("same-run")
    replayed = [second_engine.push(daily_candle(index)).to_json() for index in range(10)]
    for index in range(10, 30):
        second_engine.push(daily_candle(index))
    assert replayed == prior


def test_intraday_adr_excludes_current_session_daily_range() -> None:
    engine = CausalFeatureEngine("adr-run")
    for index in range(21):
        engine.push(daily_candle(index))
    current = daily_candle(20)
    intraday = Candle(
        symbol=current.symbol,
        timeframe=Timeframe.HOUR_1,
        open_time=current.open_time,
        close_time=current.open_time + timedelta(hours=1),
        session_date=current.session_date,
        open=current.open,
        high=current.high,
        low=current.low,
        close=current.close,
        volume=current.volume,
        is_complete=True,
        adjustment_factor=current.adjustment_factor,
        source=current.source,
        source_revision=current.source_revision,
    )
    snapshot = engine.push(intraday)
    assert snapshot.features["adr20"] == D("2")


def test_incomplete_candle_has_no_features() -> None:
    candle = daily_candle(0)
    incomplete = Candle(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        open_time=candle.open_time,
        close_time=candle.close_time,
        session_date=candle.session_date,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        is_complete=False,
        adjustment_factor=candle.adjustment_factor,
        source=candle.source,
        source_revision=candle.source_revision,
    )
    with pytest.raises(ValueError, match="completed"):
        CausalFeatureEngine("run").push(incomplete)


def test_ema_slope_uses_five_completed_bars_and_causal_adr() -> None:
    engine = CausalFeatureEngine("slope-run")
    snapshots: list[Observation] = []
    for index in range(55):
        source = daily_candle(index)
        close = D("100") + D(index) / D("100")
        snapshots.append(
            engine.push(
                replace(
                    source,
                    open=close,
                    high=close + D("1"),
                    low=close - D("1"),
                    close=close,
                    raw_open=close,
                    raw_high=close + D("1"),
                    raw_low=close - D("1"),
                    raw_close=close,
                    candle_id="",
                )
            )
        )
    assert snapshots[53].features["ema50_slope_adr"] is None
    slope = snapshots[54].features["ema50_slope_adr"]
    assert isinstance(slope, Decimal)
    assert slope > 0
