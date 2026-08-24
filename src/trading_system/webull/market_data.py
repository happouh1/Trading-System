"""Causal Webull sandbox market-data shadow normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol

from trading_system.domain import Candle, Timeframe
from trading_system.market_data.calendar import SessionCalendar
from trading_system.paper import CompletedBarEnvelope, PaperRuntime
from trading_system.serialization import canonical_hash
from trading_system.webull.contracts import WebullResponse


class WebullMarketDataError(ValueError):
    """A provider payload cannot safely enter the causal pipeline."""


class MarketDataKind(StrEnum):
    HISTORICAL = "HISTORICAL"
    STREAM = "STREAM"


class WebullMarketDataSource(Protocol):
    """Read-only provider boundary; implementations cannot expose order methods."""

    def market_snapshot(self, symbols: tuple[str, ...]) -> WebullResponse: ...

    def historical_bars(
        self, symbol: str, timespan: str, count: int
    ) -> WebullResponse: ...


@dataclass(frozen=True, slots=True)
class ShadowBar:
    candle: Candle
    provider_timestamp: datetime
    received_at: datetime
    known_at: datetime
    raw_payload_hash: str
    kind: MarketDataKind


_FIELDS = {
    "symbol", "timeframe", "open_time", "close_time", "provider_timestamp",
    "open", "high", "low", "close", "volume", "raw_open", "raw_high",
    "raw_low", "raw_close", "raw_volume", "adjustment_factor", "is_complete",
}
_SDK_HISTORY_FIELDS = {
    "close", "high", "instrument_id", "low", "open", "symbol", "tickerId",
    "time", "trading_session", "volume",
}


def _time(value: object, name: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise WebullMarketDataError(f"invalid {name}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise WebullMarketDataError(f"{name} must be timezone-aware")
    return result.astimezone(UTC)


def _number(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise WebullMarketDataError(f"invalid {name}") from exc
    if not result.is_finite():
        raise WebullMarketDataError(f"{name} must be finite")
    return result


def decode_sdk_history(
    response: WebullResponse, received_at: datetime, calendar: SessionCalendar
) -> WebullResponse:
    """Decode the captured SDK 2.0.17 M60 US-stock response."""
    received = _time(received_at, "received_at")
    values = response.payload.get("items")
    if not isinstance(values, (tuple, list)):
        raise WebullMarketDataError("Webull SDK history response lacks an items array")
    rows: list[tuple[datetime, Mapping[str, object]]] = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) != _SDK_HISTORY_FIELDS:
            raise WebullMarketDataError("unknown Webull SDK history item schema")
        if value["trading_session"] != "RTH":
            raise WebullMarketDataError("Webull SDK history item is not RTH")
        rows.append((_time(value["time"], "time"), value))
    rows.sort(key=lambda item: (str(item[1]["symbol"]), item[0]))
    bars: list[dict[str, object]] = []
    for index, (open_time, value) in enumerate(rows):
        bounds = calendar.bounds(open_time.date())
        if bounds is None or not bounds[0] <= open_time < bounds[1]:
            raise WebullMarketDataError("Webull SDK history time is outside XNYS RTH")
        if bounds[1] > received:
            raise WebullMarketDataError("Webull SDK history session is not complete")
        next_open = None
        if index + 1 < len(rows):
            candidate_time, candidate = rows[index + 1]
            if (
                candidate["symbol"] == value["symbol"]
                and candidate_time.date() == open_time.date()
            ):
                next_open = candidate_time
        close_time = bounds[1] if next_open is None else next_open
        duration = close_time - open_time
        if duration <= timedelta(0) or duration > timedelta(hours=1):
            raise WebullMarketDataError("Webull SDK M60 boundaries are invalid")
        bars.append({
            "symbol": value["symbol"], "timeframe": Timeframe.HOUR_1.value,
            "open_time": open_time, "close_time": close_time,
            "provider_timestamp": received, "open": value["open"],
            "high": value["high"], "low": value["low"], "close": value["close"],
            "volume": value["volume"], "raw_open": value["open"],
            "raw_high": value["high"], "raw_low": value["low"],
            "raw_close": value["close"], "raw_volume": value["volume"],
            "adjustment_factor": "1", "is_complete": True,
        })
    return WebullResponse(response.status_code, {"bars": tuple(bars)})


class WebullMarketDataNormalizer:
    """Stateful normalizer that rejects noncausal and revised provider bars."""

    def __init__(
        self,
        calendar: SessionCalendar,
        *,
        max_lateness_seconds: int = 120,
        latest: Mapping[tuple[str, Timeframe], datetime] | None = None,
    ) -> None:
        if max_lateness_seconds < 0:
            raise ValueError("market-data lateness cannot be negative")
        self.calendar = calendar
        self.max_lateness_seconds = max_lateness_seconds
        self._accepted: dict[tuple[str, Timeframe, datetime], str] = {}
        self._latest = dict(latest or {})

    def normalize(
        self,
        payload: Mapping[str, object],
        *,
        received_at: datetime,
        source_revision: str,
        kind: MarketDataKind,
    ) -> ShadowBar:
        if set(payload) != _FIELDS:
            raise WebullMarketDataError("Webull bar fields do not match the shadow-v1 schema")
        received = _time(received_at, "received_at")
        provider_time = _time(payload["provider_timestamp"], "provider_timestamp")
        open_time = _time(payload["open_time"], "open_time")
        close_time = _time(payload["close_time"], "close_time")
        if payload["is_complete"] is not True:
            raise WebullMarketDataError("incomplete Webull bars are unavailable")
        if provider_time < close_time or received < provider_time:
            raise WebullMarketDataError("bar timestamps violate causal availability")
        if (
            kind is MarketDataKind.STREAM
            and (received - close_time).total_seconds() > self.max_lateness_seconds
        ):
            raise WebullMarketDataError("stale Webull completed bar")
        try:
            timeframe = Timeframe(str(payload["timeframe"]))
        except ValueError as exc:
            raise WebullMarketDataError("unsupported Webull timeframe") from exc
        if timeframe is not Timeframe.HOUR_1:
            raise WebullMarketDataError(
                "provider bars must be 1h; higher timeframes require causal aggregation"
            )
        symbol = str(payload["symbol"])
        session_date = open_time.date()
        bounds = self.calendar.bounds(session_date)
        if bounds is None or open_time < bounds[0] or close_time > bounds[1]:
            raise WebullMarketDataError("Webull bar is outside the XNYS regular session")
        revision = source_revision.strip()
        if not revision:
            raise WebullMarketDataError("Webull source revision is required")
        raw_hash = canonical_hash(payload)
        key = (symbol, timeframe, open_time)
        prior_hash = self._accepted.get(key)
        if prior_hash is not None:
            reason = "duplicate" if prior_hash == raw_hash else "revised"
            raise WebullMarketDataError(f"{reason} Webull bar")
        stream_key = (symbol, timeframe)
        prior_close = self._latest.get(stream_key)
        if prior_close is not None and close_time <= prior_close:
            raise WebullMarketDataError("out-of-order Webull bar")
        factor = _number(payload["adjustment_factor"], "adjustment_factor")
        raw_values = {
            name: _number(payload[name], name)
            for name in ("raw_open", "raw_high", "raw_low", "raw_close", "raw_volume")
        }
        try:
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
                session_date=date.fromisoformat(session_date.isoformat()),
                open=_number(payload["open"], "open"),
                high=_number(payload["high"], "high"),
                low=_number(payload["low"], "low"),
                close=_number(payload["close"], "close"),
                volume=_number(payload["volume"], "volume"),
                is_complete=True,
                adjustment_factor=factor,
                source="WEBULL_SANDBOX",
                source_revision=revision,
                raw_open=raw_values["raw_open"],
                raw_high=raw_values["raw_high"],
                raw_low=raw_values["raw_low"],
                raw_close=raw_values["raw_close"],
                raw_volume=raw_values["raw_volume"],
            )
        except ValueError as exc:
            raise WebullMarketDataError(str(exc)) from exc
        self._accepted[key] = raw_hash
        self._latest[stream_key] = close_time
        return ShadowBar(candle, provider_time, received, received, raw_hash, kind)

    def normalize_many(
        self,
        payloads: Iterable[Mapping[str, object]],
        *,
        received_at: datetime,
        source_revision: str,
        kind: MarketDataKind,
    ) -> tuple[ShadowBar, ...]:
        ordered = sorted(
            payloads,
            key=lambda item: (
                str(item.get("symbol", "")), str(item.get("timeframe", "")),
                str(item.get("open_time", "")),
            ),
        )
        return tuple(
            self.normalize(
                item, received_at=received_at, source_revision=source_revision, kind=kind
            )
            for item in ordered
        )


class ShadowBarRegistryProtocol(Protocol):
    def insert_envelope(
        self, session_id: str, operation: str, occurred_at: datetime,
        response: WebullResponse, request: object | None = None,
    ) -> bool: ...

    def insert_shadow_bar(self, session_id: str, item: ShadowBar) -> bool: ...


class WebullShadowDataService:
    """Persists raw evidence before advancing the provider-neutral shadow runtime."""

    def __init__(
        self, session_id: str, normalizer: WebullMarketDataNormalizer,
        registry: ShadowBarRegistryProtocol, runtime: PaperRuntime,
    ) -> None:
        self.session_id = session_id
        self.normalizer = normalizer
        self.registry = registry
        self.runtime = runtime

    def ingest(
        self, response: WebullResponse, *, received_at: datetime,
        source_revision: str, kind: MarketDataKind,
    ) -> tuple[ShadowBar, ...]:
        self.registry.insert_envelope(
            self.session_id, f"MARKET_{kind.value}", received_at, response
        )
        if not 200 <= response.status_code < 300:
            raise WebullMarketDataError("Webull market-data request failed")
        raw_bars = response.payload.get("bars")
        if not isinstance(raw_bars, (tuple, list)):
            raise WebullMarketDataError("Webull response lacks a bars array")
        bars: list[Mapping[str, object]] = []
        for value in raw_bars:
            if not isinstance(value, Mapping):
                raise WebullMarketDataError("Webull bars must be objects")
            bars.append({str(key): item for key, item in value.items()})
        normalized = self.normalizer.normalize_many(
            bars, received_at=received_at, source_revision=source_revision, kind=kind
        )
        for item in normalized:
            self.registry.insert_shadow_bar(self.session_id, item)
            if kind is MarketDataKind.STREAM:
                self.runtime.process_completed_bar(
                    CompletedBarEnvelope(
                        item.candle, item.received_at, item.candle.source_revision
                    ),
                    item.known_at,
                )
        return normalized

    def ingest_sdk_history(
        self, response: WebullResponse, *, received_at: datetime
    ) -> tuple[ShadowBar, ...]:
        self.registry.insert_envelope(
            self.session_id, "MARKET_HISTORICAL_RAW", received_at, response
        )
        if not 200 <= response.status_code < 300:
            raise WebullMarketDataError("Webull market-data request failed")
        revision = canonical_hash({"provider": "WEBULL_SANDBOX", "response": response})
        decoded = decode_sdk_history(response, received_at, self.normalizer.calendar)
        return self.ingest(
            decoded, received_at=received_at, source_revision=revision,
            kind=MarketDataKind.HISTORICAL,
        )
