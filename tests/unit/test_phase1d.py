from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_features import daily_candle
from trading_system.backtest import TradeResult, summarize
from trading_system.domain import Direction, Timeframe
from trading_system.learning import label_outcome
from trading_system.learning.exports import write_observations
from trading_system.replay import ReplayEngine
from trading_system.reporting import export_jsonl, markdown_report

D = Decimal


def test_replay_normalizes_input_and_uses_htf_order_at_same_close() -> None:
    base = daily_candle(0)
    hour = replace(
        base,
        timeframe=Timeframe.HOUR_1,
        open_time=base.close_time - timedelta(hours=1),
        candle_id="",
    )
    records, checkpoint = ReplayEngine(lambda candle: candle.timeframe.value).run([hour, base])
    assert tuple(record.candle.timeframe for record in records) == (
        Timeframe.DAY_1,
        Timeframe.HOUR_1,
    )
    assert checkpoint is not None
    assert checkpoint.processed_candles == 2


def test_replay_is_deterministic_and_resume_excludes_checkpoint_time() -> None:
    candles = tuple(daily_candle(index) for index in range(3))
    first, checkpoint = ReplayEngine(lambda candle: candle.candle_id).run(reversed(candles))
    second, repeated = ReplayEngine(lambda candle: candle.candle_id).run(candles)
    assert export_jsonl(first) == export_jsonl(second)
    assert checkpoint == repeated
    assert checkpoint is not None
    resumed, _ = ReplayEngine(lambda candle: candle.candle_id).run(
        candles,
        resume_after=candles[1].close_time,
        processed_before=2,
    )
    assert tuple(record.candle for record in resumed) == (candles[2],)


def test_replay_rejects_duplicates() -> None:
    candle = daily_candle(0)
    with pytest.raises(ValueError, match="duplicate"):
        ReplayEngine(lambda item: item).run((candle, candle))


def test_outcome_uses_only_provided_future_bars() -> None:
    base = daily_candle(0)
    future = (
        replace(
            daily_candle(1),
            high=D("102"),
            close=D("101"),
            raw_high=D("102"),
            raw_close=D("101"),
            candle_id="",
        ),
        replace(
            daily_candle(2),
            high=D("104"),
            close=D("103"),
            raw_high=D("104"),
            raw_close=D("103"),
            candle_id="",
        ),
    )
    outcome = label_outcome(
        run_id="run-1",
        observation_id="observation-1",
        label_version="1.0.0",
        direction=Direction.LONG,
        entry=base.close,
        risk=D("2"),
        future_candles=future,
    )
    assert outcome.horizon_bars == 2
    assert outcome.mfe_r == D("2")
    assert outcome.time_to_2r == 2
    assert outcome.label_available_at == future[-1].close_time


def test_metrics_and_report_disclose_biases() -> None:
    metrics = summarize(
        (
            TradeResult("a", D("2"), D("2.5"), D("0.5"), 3),
            TradeResult("b", D("-1"), D("0.2"), D("1"), 2),
        )
    )
    assert metrics.expectancy_r == D("0.5")
    assert metrics.profit_factor == D("2")
    report = markdown_report("run-1", metrics)
    assert "survivorship bias" in report
    assert "adverse-first" in report


def test_empty_metrics_are_defined() -> None:
    metrics = summarize(())
    assert metrics.trade_count == 0
    assert metrics.profit_factor is None


def test_fixture_clock_is_utc() -> None:
    assert datetime(2026, 1, 1, tzinfo=UTC).utcoffset() == timedelta(0)


def test_csv_observation_export_is_deterministic(tmp_path: Path) -> None:
    target = tmp_path / "observations.csv"
    rows = ({"known_at": "2026-01-01T00:00:00Z", "config_hash": "sha256:cfg"},)
    write_observations(rows, target, "csv")
    first = target.read_bytes()
    write_observations(rows, target, "csv")
    assert target.read_bytes() == first
    assert b"config_hash" in first
