from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_features import daily_candle
from trading_system.patterns import (
    BaseBar,
    RangeBoundary,
    RangeBoxDetector,
    RangeReclaimConfigError,
    VolumePointOfControl,
    assign_parent_box,
    load_range_reclaim_config,
)

ROOT = Path(__file__).parents[2]
D = Decimal


def config_path() -> Path:
    return ROOT / "config/range_reclaim.phase7a.v1.yaml"


def fixture_bars(*, dual_boundary_index: int | None = None) -> list[BaseBar]:
    bars = [
        BaseBar(daily_candle(index), D("2"), D("2"))
        for index in range(40)
    ]
    for offset in range(8):
        candle = daily_candle(40 + offset)
        if offset == dual_boundary_index:
            low, high = D("99"), D("101")
        elif offset % 2 == 0:
            low, high = D("99"), D("100.4")
        else:
            low, high = D("99.6"), D("101")
        candle = replace(
            candle,
            high=high,
            low=low,
            raw_high=high,
            raw_low=low,
        )
        bars.append(BaseBar(candle, D("2"), D("1")))
    return bars


def detector() -> RangeBoxDetector:
    return RangeBoxDetector(load_range_reclaim_config(config_path()), code_version="test")


def test_detects_alternating_distinct_rotations_deterministically() -> None:
    bars = fixture_bars()
    first = detector().detect(bars)
    second = detector().detect(list(bars))
    assert first is not None
    assert first == second
    assert first.lower == D("99")
    assert first.upper == D("101")
    assert first.geometric_midpoint == D("100")
    assert first.volume_poc is None
    assert first.lower_episode_count == 4
    assert first.upper_episode_count == 4
    assert [item.boundary for item in first.episodes] == [
        RangeBoundary.LOWER,
        RangeBoundary.UPPER,
    ] * 4


def test_consecutive_same_boundary_contacts_collapse_to_one_episode() -> None:
    bars = fixture_bars()
    bars[41] = replace(
        bars[41],
        candle=replace(
            bars[41].candle,
            high=D("100.4"),
            low=D("99"),
            raw_high=D("100.4"),
            raw_low=D("99"),
        ),
    )
    result = detector().detect(bars)
    assert result is not None
    assert result.episodes[0].boundary is RangeBoundary.LOWER
    assert len(result.episodes[0].candle_ids) >= 2
    assert all(
        left.boundary is not right.boundary
        for left, right in zip(result.episodes, result.episodes[1:], strict=False)
    )


def test_ambiguous_dual_boundary_bar_fails_closed() -> None:
    assert detector().detect(fixture_bars(dual_boundary_index=3)) is None


def test_input_order_and_incomplete_candles_are_rejected() -> None:
    bars = fixture_bars()
    with pytest.raises(ValueError, match="chronological"):
        detector().detect(list(reversed(bars)))
    bars[-1] = replace(bars[-1], candle=replace(bars[-1].candle, is_complete=False))
    with pytest.raises(ValueError, match="completed"):
        detector().detect(bars)


def test_observed_volume_poc_is_separate_and_causal() -> None:
    bars = fixture_bars()
    known_at = bars[-1].candle.close_time
    poc = VolumePointOfControl(D("100.25"), known_at, "tape-v1", "vap-v1")
    result = detector().detect(bars, volume_poc=poc)
    assert result is not None
    assert result.geometric_midpoint == D("100")
    assert result.volume_poc == poc
    future_poc = replace(poc, known_at=known_at + timedelta(microseconds=1))
    with pytest.raises(ValueError, match="future"):
        detector().detect(bars, volume_poc=future_poc)


def test_parent_assignment_is_causal_and_selects_narrowest_container() -> None:
    child = detector().detect(fixture_bars())
    assert child is not None
    earlier = timedelta(days=20)
    earlier_episodes = tuple(
        replace(episode, known_at=episode.known_at - earlier)
        for episode in child.episodes
    )
    wide = replace(
        child,
        box_id="wide",
        lower=D("95"),
        upper=D("105"),
        geometric_midpoint=D("100"),
        start_time=child.start_time - earlier,
        end_time=child.end_time - earlier,
        known_at=child.known_at - earlier,
        episodes=earlier_episodes,
    )
    narrow = replace(
        wide,
        box_id="narrow",
        lower=D("98"),
        upper=D("102"),
        geometric_midpoint=D("100"),
    )
    future = replace(narrow, box_id="future", known_at=child.known_at + timedelta(days=1))
    assigned = assign_parent_box(child, [wide, future, narrow])
    assert assigned.parent_box_id == "narrow"
    assert assigned.box_id == child.box_id


def test_config_is_hashed_and_authority_is_locked(tmp_path: Path) -> None:
    config = load_range_reclaim_config(config_path())
    assert config.config_hash.startswith("sha256:")
    assert config.min_bars == 8
    assert config.contact_tolerance_adr == D("0.1")
    raw = json.loads(config_path().read_text(encoding="utf-8"))
    raw["authority"]["scoring_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReclaimConfigError, match="research-only"):
        load_range_reclaim_config(unsafe)
