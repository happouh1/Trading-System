from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_features import daily_candle
from tests.unit.test_phase7a_range_reclaim import fixture_bars
from trading_system.patterns import (
    BaseBar,
    RangeBoxDetector,
    RangeResearchConfigError,
    RangeResearchReplay,
    RangeTerminalLocation,
    label_range_box,
    load_range_reclaim_config,
    load_range_research_config,
)

ROOT = Path(__file__).parents[2]
D = Decimal


def replay() -> RangeResearchReplay:
    detector = RangeBoxDetector(
        load_range_reclaim_config(ROOT / "config/range_reclaim.phase7a.v1.yaml"),
        code_version="test",
    )
    return RangeResearchReplay(
        detector,
        load_range_research_config(ROOT / "config/range_reclaim.phase7b.v1.yaml"),
        code_version="test",
    )


def research_bars(future_count: int = 6) -> list[BaseBar]:
    bars = fixture_bars()
    bars.extend(
        BaseBar(daily_candle(index), D("2"), D("2"))
        for index in range(48, 48 + future_count)
    )
    return bars


def test_replay_detects_only_prefix_boxes_and_releases_mature_outcomes() -> None:
    result = replay().run(research_bars())
    assert result.boxes
    first = result.boxes[0]
    assert first.known_at == next(
        bar.candle.close_time
        for bar in research_bars()
        if bar.candle.candle_id == first.end_candle_id
    )
    horizons = {item.horizon_bars for item in result.outcomes if item.box_id == first.box_id}
    assert horizons == {1, 3, 5}
    assert all(item.label_available_at > first.known_at for item in result.outcomes)


def test_replay_is_deterministic_and_rejects_reordered_input() -> None:
    bars = research_bars(3)
    assert replay().run(bars) == replay().run(list(bars))
    with pytest.raises(ValueError, match="chronological"):
        replay().run(list(reversed(bars)))


def test_neutral_label_uses_box_units_and_strict_terminal_location() -> None:
    bars = fixture_bars()
    box = replay().detector.detect(bars)
    assert box is not None
    future = daily_candle(48)
    future = replace(
        future,
        close=D("102"),
        high=D("103"),
        low=D("98"),
        raw_close=D("102"),
        raw_high=D("103"),
        raw_low=D("98"),
    )
    outcome = label_range_box(
        box,
        anchor_close=D("100"),
        future_candles=(future,),
        config_hash="sha256:test",
        code_version="test",
    )
    assert outcome.terminal_location is RangeTerminalLocation.ABOVE
    assert outcome.forward_return == D("0.02")
    assert outcome.maximum_upside_box_units == D("1.5")
    assert outcome.maximum_downside_box_units == D("1")


def test_labels_reject_future_series_mismatch() -> None:
    box = replay().detector.detect(fixture_bars())
    assert box is not None
    wrong = replace(daily_candle(48), symbol="MSFT")
    with pytest.raises(ValueError, match="match the box"):
        label_range_box(
            box,
            anchor_close=D("100"),
            future_candles=(wrong,),
            config_hash="sha256:test",
            code_version="test",
        )


def test_phase7b_config_is_strict_and_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7b.v1.yaml"
    config = load_range_research_config(path)
    assert config.horizons(fixture_bars()[-1].candle.timeframe) == (1, 3, 5, 10, 20, 60)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["scoring_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeResearchConfigError, match="research-only"):
        load_range_research_config(unsafe)
