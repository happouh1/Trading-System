from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading_system.domain import Direction, Timeframe
from trading_system.scoring import (
    ConfidenceComponents,
    LocationComponents,
    TimeframeState,
    asof_join,
    confidence_score,
    location_score,
    mtf_score,
)
from trading_system.structure import StructureState

D = Decimal
NOW = datetime(2026, 1, 5, 20, 0, tzinfo=UTC)


def test_asof_join_never_exposes_unclosed_higher_timeframe() -> None:
    values = [
        TimeframeState(Timeframe.DAY_1, NOW - timedelta(hours=1), "daily-old", StructureState.UPTREND),
        TimeframeState(Timeframe.DAY_1, NOW + timedelta(hours=1), "daily-future", StructureState.DOWNTREND),
        TimeframeState(Timeframe.HOUR_1, NOW, "hour-current", StructureState.UPTREND),
    ]
    snapshot = asof_join(NOW, values)
    assert snapshot.source_candle_ids == ("daily-old", "hour-current")
    assert all(item.close_time <= snapshot.known_at for item in snapshot.states)


def test_mtf_alignment_is_directionally_symmetric() -> None:
    values = [
        TimeframeState(timeframe, NOW, timeframe.value, StructureState.UPTREND)
        for timeframe in Timeframe
    ]
    snapshot = asof_join(NOW, values)
    assert mtf_score(snapshot, Direction.LONG) == D("100")
    assert mtf_score(snapshot, Direction.SHORT) == D("0")


def test_location_and_confidence_caps_are_deterministic() -> None:
    location = location_score(LocationComponents(D("0"), D("2"), D("0.5"), D("0.2")))
    assert location == D("96.00")
    components = ConfidenceComponents(*(D("100") for _ in range(9)))
    result = confidence_score(components, volume_unavailable=True, data_quality_warning=True)
    assert result.raw_score == D("100")
    assert result.final_score == D("49")
    assert result.applied_caps == ("VOLUME_UNAVAILABLE", "DATA_QUALITY_WARNING")
