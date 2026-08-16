from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from trading_system.domain import Direction, LevelKind, Timeframe
from trading_system.levels import LevelEngine, LevelSource, runway_adr

D = Decimal
START = datetime(2026, 1, 5, tzinfo=UTC)


def source(
    source_id: str,
    price: str,
    offset: int,
    *,
    timeframe: Timeframe = Timeframe.HOUR_1,
    kind: LevelKind = LevelKind.SWING_HIGH,
) -> LevelSource:
    return LevelSource(
        source_id=source_id,
        symbol="AAPL",
        timeframe=timeframe,
        known_at=START + timedelta(hours=offset),
        price=D(price),
        kind=kind,
        evidence_candle_ids=(f"candle-{source_id}",),
    )


def test_clustering_is_input_order_independent() -> None:
    inputs = [source("a", "100", 0), source("b", "100.20", 1), source("c", "105", 2)]
    engine = LevelEngine()
    forward = engine.build("run-1", inputs, D("2"))
    reverse = engine.build("run-1", list(reversed(inputs)), D("2"))
    assert forward == reverse
    assert len(forward) == 2
    assert forward[0].lower_price == D("99.90")
    assert forward[0].upper_price == D("100.30")


def test_confluence_uses_distinct_timeframe_flags_and_padding() -> None:
    inputs = [
        source("weekly", "100", 0, timeframe=Timeframe.WEEK_1),
        source("daily", "100.1", 1, timeframe=Timeframe.DAY_1),
    ]
    level = LevelEngine().build("run-1", inputs, D("2"))[0]
    assert level.confluence_score == D("44")
    assert level.known_at == inputs[1].known_at


def test_runway_uses_nearest_opposing_zone_boundary() -> None:
    zones = LevelEngine().build(
        "run-1", [source("near", "103", 0), source("far", "108", 1)], D("2")
    )
    assert runway_adr(D("100"), Direction.LONG, zones, D("2")) == D("1.45")
    assert runway_adr(D("110"), Direction.SHORT, zones, D("2")) == D("0.95")
    assert runway_adr(D("110"), Direction.LONG, zones, D("2")) is None
    with pytest.raises(ValueError, match="NONE"):
        runway_adr(D("100"), Direction.NONE, zones, D("2"))
