from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.domain import Timeframe
from trading_system.market_data import StaticSessionCalendar
from trading_system.paper import (
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
)
from trading_system.persistence import SQLiteRepository
from trading_system.webull import (
    MarketDataKind,
    WebullMarketDataError,
    WebullMarketDataNormalizer,
    WebullRegistry,
    WebullResponse,
    WebullShadowDataService,
    decode_sdk_history,
)

ROOT = Path(__file__).parents[2]
OPEN = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
CLOSE = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)
RECEIVED = datetime(2026, 1, 5, 15, 30, 2, tzinfo=UTC)


def payload() -> dict[str, object]:
    raw = json.loads(
        (ROOT / "tests/fixtures/webull_shadow_bars_v1.json").read_text(encoding="utf-8")
    )
    assert isinstance(raw, dict) and isinstance(raw["bars"], list)
    item = raw["bars"][0]
    assert isinstance(item, dict)
    return item


def calendar() -> StaticSessionCalendar:
    return StaticSessionCalendar({date(2026, 1, 5): (OPEN, CLOSE)})


def test_strict_shadow_normalization_is_causal_and_deterministic() -> None:
    normalizer = WebullMarketDataNormalizer(calendar())
    bar = normalizer.normalize(
        payload(), received_at=RECEIVED, source_revision="webull-fixture-v1",
        kind=MarketDataKind.HISTORICAL,
    )
    assert bar.known_at == RECEIVED
    assert bar.candle.close_time < bar.known_at
    assert bar.candle.source == "WEBULL_SANDBOX"
    assert bar.candle.raw_close == bar.candle.close
    assert bar.candle.timeframe is Timeframe.HOUR_1
    assert bar.raw_payload_hash.startswith("sha256:")


@pytest.mark.parametrize("mutation,match", [
    ({"is_complete": False}, "incomplete"),
    ({"open_time": "2026-01-05T13:30:00Z"}, "outside"),
    ({"provider_timestamp": "2026-01-05T15:29:59Z"}, "causal"),
])
def test_invalid_shadow_bars_fail_closed(
    mutation: dict[str, object], match: str
) -> None:
    item = {**payload(), **mutation}
    with pytest.raises(WebullMarketDataError, match=match):
        WebullMarketDataNormalizer(calendar()).normalize(
            item, received_at=RECEIVED, source_revision="revision",
            kind=MarketDataKind.STREAM,
        )


def test_duplicate_revision_order_and_staleness_are_rejected() -> None:
    normalizer = WebullMarketDataNormalizer(calendar())
    item = payload()
    normalizer.normalize(
        item, received_at=RECEIVED, source_revision="revision",
        kind=MarketDataKind.HISTORICAL,
    )
    with pytest.raises(WebullMarketDataError, match="duplicate"):
        normalizer.normalize(
            item, received_at=RECEIVED, source_revision="revision",
            kind=MarketDataKind.HISTORICAL,
        )
    with pytest.raises(WebullMarketDataError, match="stale"):
        WebullMarketDataNormalizer(calendar()).normalize(
            item, received_at=RECEIVED + timedelta(minutes=3), source_revision="revision",
            kind=MarketDataKind.STREAM,
        )


def test_input_permutations_normalize_to_causal_order() -> None:
    first = payload()
    second = {
        **first,
        "open_time": "2026-01-05T15:30:00Z",
        "close_time": "2026-01-05T16:30:00Z",
        "provider_timestamp": "2026-01-05T16:30:01Z",
    }
    bars = WebullMarketDataNormalizer(calendar()).normalize_many(
        (second, first), received_at=datetime(2026, 1, 5, 17, tzinfo=UTC),
        source_revision="revision", kind=MarketDataKind.HISTORICAL,
    )
    assert tuple(item.candle.open_time for item in bars) == (
        datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 5, 15, 30, tzinfo=UTC),
    )


def test_captured_sdk_history_schema_uses_next_start_and_session_close() -> None:
    session_date = date(2026, 8, 21)
    session_open = datetime(2026, 8, 21, 13, 30, tzinfo=UTC)
    session_close = datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
    captured = WebullResponse(200, {"items": (
        {"symbol": "AAPL", "time": "2026-08-21T19:00:00.000+0000",
         "open": "227", "high": "228", "low": "226", "close": "227.5",
         "volume": "100", "trading_session": "RTH", "instrument_id": "redacted",
         "tickerId": "redacted"},
        {"symbol": "AAPL", "time": "2026-08-21T18:30:00.000+0000",
         "open": "226", "high": "227", "low": "225", "close": "226.5",
         "volume": "200", "trading_session": "RTH", "instrument_id": "redacted",
         "tickerId": "redacted"},
    )})
    decoded = decode_sdk_history(
        captured, datetime(2026, 8, 24, tzinfo=UTC),
        StaticSessionCalendar({session_date: (session_open, session_close)}),
    )
    bars = decoded.payload["bars"]
    assert isinstance(bars, tuple)
    assert bars[0]["open_time"] == datetime(2026, 8, 21, 18, 30, tzinfo=UTC)
    assert bars[0]["close_time"] == datetime(2026, 8, 21, 19, 0, tzinfo=UTC)
    assert bars[1]["close_time"] == session_close


def test_shadow_pipeline_persists_candle_evidence_and_checkpoint(tmp_path: Path) -> None:
    database = tmp_path / "shadow.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession("shadow", OPEN, PaperMode.SHADOW, "code", "config", "data", "XNYS")
        )
        runtime = PaperRuntime(paper, "shadow", PaperMode.SHADOW, InternalSimulatorAdapter())
        runtime.start(OPEN)
        service = WebullShadowDataService(
            "shadow", WebullMarketDataNormalizer(calendar()), WebullRegistry(repository), runtime
        )
        bars = service.ingest(
            WebullResponse(200, {"bars": (payload(),)}), received_at=RECEIVED,
            source_revision="webull-fixture-v1", kind=MarketDataKind.STREAM,
        )
        assert len(bars) == 1
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM webull_shadow_bars"
        ).fetchone() == (1,)
        assert paper.latest_checkpoint("shadow") is not None
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert repository.connection.execute(
            "SELECT raw_payload_hash, known_at FROM webull_shadow_bars"
        ).fetchone() == (bars[0].raw_payload_hash, "2026-01-05T15:30:02.000000Z")
