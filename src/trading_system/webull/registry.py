"""Append-only redacted Webull sandbox persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id
from trading_system.webull.contracts import AccountVerification, WebullResponse, WebullStockOrder
from trading_system.webull.market_data import ShadowBar
from trading_system.webull.security import redact


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Webull registry timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class WebullRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def _insert(self, table: str, identity_column: str, identity: str,
                columns: tuple[str, ...], values: tuple[object, ...], payload: object) -> bool:
        payload_json, payload_hash = canonical_json(payload), canonical_hash(payload)
        names = (*columns, "payload_json", "payload_hash")
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(names)}) VALUES "
            f"({','.join('?' for _ in names)})", (*values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?", (identity,)
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload: {identity}")
            return False
        self.repository.connection.commit()
        return True

    def insert_verification(self, item: AccountVerification) -> bool:
        return self._insert(
            "webull_connection_verifications", "verification_id", item.verification_id,
            ("verification_id", "session_id", "occurred_at", "account_id_hash"),
            (item.verification_id, item.session_id,
             _time(item.occurred_at), item.account_id_hash),
            item,
        )

    def insert_shadow_bar(self, session_id: str, item: ShadowBar) -> bool:
        self.repository.insert_candle(item.candle)
        shadow_bar_id = deterministic_id(
            "webull_shadow_bar", (session_id, item.candle.candle_id)
        )
        payload = {
            "shadow_bar_id": shadow_bar_id,
            "session_id": session_id,
            "candle": item.candle,
            "kind": item.kind,
            "provider_timestamp": item.provider_timestamp,
            "received_at": item.received_at,
            "known_at": item.known_at,
            "raw_payload_hash": item.raw_payload_hash,
        }
        return self._insert(
            "webull_shadow_bars", "shadow_bar_id", shadow_bar_id,
            ("shadow_bar_id", "session_id", "candle_id", "kind",
             "provider_timestamp", "received_at", "known_at", "raw_payload_hash",
             "source_revision"),
            (shadow_bar_id, session_id, item.candle.candle_id, item.kind.value,
             _time(item.provider_timestamp), _time(item.received_at), _time(item.known_at),
             item.raw_payload_hash, item.candle.source_revision),
            payload,
        )

    def latest_shadow_close(self, session_id: str) -> datetime | None:
        row = self.repository.connection.execute(
            "SELECT MAX(known_at) FROM webull_shadow_bars WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).astimezone(UTC)

    def insert_envelope(self, session_id: str, operation: str, occurred_at: datetime,
                        response: WebullResponse, request: object | None = None) -> bool:
        redacted_payload = redact(response.payload)
        if not isinstance(redacted_payload, dict):
            raise TypeError("redacted Webull response must remain a mapping")
        response = WebullResponse(response.status_code, redacted_payload)
        request_hash = None if request is None else canonical_hash(request)
        response_hash = canonical_hash(response)
        envelope_id = deterministic_id(
            "webull_envelope", (session_id, operation, occurred_at, request_hash, response_hash)
        )
        payload = {"envelope_id": envelope_id, "session_id": session_id,
                   "operation": operation, "occurred_at": occurred_at,
                   "request_hash": request_hash, "response": response}
        return self._insert(
            "webull_envelopes", "envelope_id", envelope_id,
            ("envelope_id", "session_id", "operation", "occurred_at",
             "request_hash", "response_hash"),
            (envelope_id, session_id, operation, _time(occurred_at),
             request_hash, response_hash), payload,
        )

    def insert_preview(self, session_id: str, intent_id: str, occurred_at: datetime,
                       order: WebullStockOrder, response: WebullResponse) -> str:
        request_hash = canonical_hash(order)
        preview_id = deterministic_id("webull_preview", (session_id, intent_id, request_hash))
        accepted = 200 <= response.status_code < 300
        payload = {"preview_id": preview_id, "session_id": session_id, "intent_id": intent_id,
                   "occurred_at": occurred_at, "request_hash": request_hash,
                   "accepted": accepted, "response": response}
        self._insert(
            "webull_order_previews", "preview_id", preview_id,
            ("preview_id", "session_id", "intent_id", "request_hash", "occurred_at", "accepted"),
            (preview_id, session_id, intent_id, request_hash,
             _time(occurred_at), int(accepted)),
            payload,
        )
        return preview_id

    def accepted_preview(self, session_id: str, intent_id: str, request_hash: str) -> bool:
        row = self.repository.connection.execute(
            """SELECT accepted FROM webull_order_previews
               WHERE session_id = ? AND intent_id = ? AND request_hash = ?""",
            (session_id, intent_id, request_hash),
        ).fetchone()
        return bool(row == (1,))

    def insert_mapping(self, session_id: str, intent_id: str,
                       order: WebullStockOrder, response: WebullResponse) -> bool:
        request_hash = canonical_hash(order)
        mapping_id = deterministic_id("webull_mapping", (session_id, intent_id))
        broker_order_id = response.payload.get("order_id")
        broker_id = str(broker_order_id) if broker_order_id is not None else None
        payload = {"mapping_id": mapping_id, "session_id": session_id, "intent_id": intent_id,
                   "client_order_id": order.client_order_id, "request_hash": request_hash,
                   "broker_order_id": broker_id, "response": response}
        return self._insert(
            "webull_client_orders", "mapping_id", mapping_id,
            ("mapping_id", "session_id", "intent_id", "client_order_id",
             "request_hash", "broker_order_id"),
            (mapping_id, session_id, intent_id, order.client_order_id,
            request_hash, broker_id), payload,
        )

    def has_mapping(self, session_id: str, intent_id: str, request_hash: str) -> bool:
        row = self.repository.connection.execute(
            """SELECT 1 FROM webull_client_orders
               WHERE session_id = ? AND intent_id = ? AND request_hash = ?""",
            (session_id, intent_id, request_hash),
        ).fetchone()
        return bool(row == (1,))
