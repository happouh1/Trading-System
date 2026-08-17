from __future__ import annotations

from decimal import Decimal

from tests.unit.test_features import daily_candle
from trading_system.patterns import BaseBar, BaseDetector

D = Decimal


def fixture_bars(count: int = 48) -> list[BaseBar]:
    return [
        BaseBar(
            candle=daily_candle(index),
            adr20=D("10"),
            atr10=D("2") if index < 40 else D("1"),
        )
        for index in range(count)
    ]


def test_valid_base_uses_only_prior_compression_history() -> None:
    bars = fixture_bars()
    detected = BaseDetector().detect(bars)
    assert detected is not None
    assert detected.bars == 8
    assert detected.start_candle_id == bars[40].candle.candle_id
    assert detected.end_candle_id == bars[47].candle.candle_id
    assert detected.width_adr == D("0.2")
    assert detected.atr_compression == D("0.5")
    assert detected.lower_touches == 8
    assert detected.upper_touches == 8


def test_future_bars_do_not_change_prior_base_result() -> None:
    bars = fixture_bars()
    before = BaseDetector().detect(bars)
    extended = [*bars, BaseBar(daily_candle(48), D("10"), D("1"))]
    assert BaseDetector().detect(bars) == before
    assert BaseDetector().detect(extended) is not None


def test_multiple_valid_windows_select_highest_quality_then_longest() -> None:
    bars = fixture_bars(49)
    detected = BaseDetector().detect(bars)
    assert detected is not None
    assert detected.bars == 9
    assert detected.start_candle_id == bars[40].candle.candle_id
