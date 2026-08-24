"""Deterministic read-only Webull streaming controls."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from trading_system.paper import PaperRuntime
from trading_system.serialization import canonical_hash, deterministic_id


class StreamState(StrEnum):
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    RECONCILING = "RECONCILING"
    HALTED = "HALTED"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class StreamNotification:
    notification_id: str
    session_id: str
    topic: str
    symbol: str | None
    provider_timestamp: datetime | None
    received_at: datetime
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        for value in (self.received_at,):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("stream timestamps must be timezone-aware")
        if self.provider_timestamp is not None and (
            self.provider_timestamp.tzinfo is None
            or self.provider_timestamp.utcoffset() is None
        ):
            raise ValueError("stream timestamps must be timezone-aware")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class StreamRegistry(Protocol):
    def insert_stream_notification(self, item: StreamNotification) -> bool: ...
    def insert_stream_event(
        self, session_id: str, occurred_at: datetime, event_type: str,
        attempt: int, delay_seconds: int | None, payload: object,
    ) -> bool: ...

    def stream_cursor(self, session_id: str) -> dict[str, tuple[datetime, str]]: ...


def _provider_time(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


class WebullStreamCoordinator:
    def __init__(
        self, session_id: str, registry: StreamRegistry, runtime: PaperRuntime,
        *, stale_seconds: int = 120, reconnect_delays: tuple[int, ...] = (1, 2, 4),
        restore_cursor: bool = True,
    ) -> None:
        if stale_seconds < 0 or not reconnect_delays or any(
            delay <= 0 for delay in reconnect_delays
        ):
            raise ValueError("invalid deterministic streaming thresholds")
        self.session_id = session_id
        self.registry = registry
        self.runtime = runtime
        self.stale_seconds = stale_seconds
        self.reconnect_delays = reconnect_delays
        self.state = StreamState.CONNECTING
        self._last = registry.stream_cursor(session_id) if restore_cursor else {}
        self._attempt = 0

    def connected(self, occurred_at: datetime) -> None:
        if self.state is not StreamState.CONNECTING:
            raise ValueError("stream cannot connect from its current state")
        self.state = StreamState.ACTIVE
        self._attempt = 0
        self.registry.insert_stream_event(
            self.session_id, occurred_at, "CONNECTED", 0, None, {"read_only": True}
        )

    def notification(
        self, topic: str, payload: Mapping[str, object], received_at: datetime
    ) -> bool:
        if self.state is not StreamState.ACTIVE:
            raise ValueError("stream is not active")
        raw_symbol = payload.get("symbol")
        symbol = raw_symbol if isinstance(raw_symbol, str) and raw_symbol else None
        provider_at = _provider_time(payload.get("timestamp"))
        payload_hash = canonical_hash(payload)
        item = StreamNotification(
            deterministic_id(
                "webull_stream_notification",
                (self.session_id, topic, symbol, provider_at, received_at, payload_hash),
            ),
            self.session_id, topic, symbol, provider_at, received_at, payload,
        )
        inserted = self.registry.insert_stream_notification(item)
        if topic != "snapshot" or payload.get("trading_session") != "RTH":
            self._halt(received_at, "UNSUPPORTED_STREAM_MESSAGE")
            raise ValueError("only RTH snapshot notifications are allowed")
        if symbol is None or symbol != symbol.upper():
            self._halt(received_at, "INVALID_STREAM_SYMBOL")
            raise ValueError("invalid stream symbol")
        if provider_at is None:
            self._halt(received_at, "INVALID_STREAM_TIMESTAMP")
            raise ValueError("stream timestamp must be epoch milliseconds")
        if provider_at > received_at:
            self._halt(received_at, "FUTURE_STREAM_TIMESTAMP")
            raise ValueError("stream provider timestamp is in the future")
        prior = self._last.get(symbol)
        if prior is not None and provider_at == prior[0] and payload_hash == prior[1]:
            return False
        if prior is not None and provider_at <= prior[0]:
            self._halt(received_at, "OUT_OF_ORDER_STREAM_MESSAGE")
            raise ValueError("out-of-order stream notification")
        if (received_at - provider_at).total_seconds() > self.stale_seconds:
            self._halt(received_at, "STALE_STREAM_MESSAGE")
            raise ValueError("stale stream notification")
        self._last[symbol] = (provider_at, payload_hash)
        return inserted

    def disconnected(self, occurred_at: datetime, reason: str) -> int:
        self.state = StreamState.RECONCILING
        if self._attempt >= len(self.reconnect_delays):
            self._halt(occurred_at, "STREAM_RECONNECT_EXHAUSTED")
            raise ValueError("stream reconnect attempts exhausted")
        delay = self.reconnect_delays[self._attempt]
        self._attempt += 1
        self.registry.insert_stream_event(
            self.session_id, occurred_at, "DISCONNECTED", self._attempt, delay,
            {"reason": reason},
        )
        return delay

    def reconciled(self, occurred_at: datetime, matched: bool) -> None:
        self.registry.insert_stream_event(
            self.session_id, occurred_at, "REST_RECONCILIATION", self._attempt, None,
            {"matched": matched},
        )
        if not matched:
            self._halt(occurred_at, "STREAM_RECONCILIATION_MISMATCH")
            raise ValueError("stream REST reconciliation mismatch")
        self.state = StreamState.CONNECTING

    def _halt(self, occurred_at: datetime, reason: str) -> None:
        self.state = StreamState.HALTED
        self.registry.insert_stream_event(
            self.session_id, occurred_at, "HALTED", self._attempt, None, {"reason": reason}
        )
        self.runtime.halt(occurred_at, reason)
