"""Append-only redacted Webull sandbox persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id
from trading_system.webull.contracts import (
    AccountVerification,
    WebullEntryRelease,
    WebullOrderSnapshot,
    WebullReconciliation,
    WebullResponse,
    WebullStockOrder,
    WebullSubmissionEventType,
)
from trading_system.webull.market_data import ShadowBar
from trading_system.webull.security import redact
from trading_system.webull.streaming import StreamNotification


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

    def insert_stream_notification(self, item: StreamNotification) -> bool:
        return self._insert(
            "webull_stream_notifications", "notification_id", item.notification_id,
            ("notification_id", "session_id", "topic", "symbol",
             "provider_timestamp", "received_at", "raw_payload_hash"),
            (item.notification_id, item.session_id, item.topic, item.symbol,
             None if item.provider_timestamp is None else _time(item.provider_timestamp),
             _time(item.received_at), canonical_hash(item.payload)),
            item,
        )

    def insert_stream_event(
        self, session_id: str, occurred_at: datetime, event_type: str,
        attempt: int, delay_seconds: int | None, payload: object,
    ) -> bool:
        event_id = deterministic_id(
            "webull_stream_event",
            (session_id, occurred_at, event_type, attempt, delay_seconds, payload),
        )
        body = {
            "stream_event_id": event_id, "session_id": session_id,
            "occurred_at": occurred_at, "event_type": event_type,
            "attempt": attempt, "delay_seconds": delay_seconds, "detail": payload,
        }
        return self._insert(
            "webull_stream_events", "stream_event_id", event_id,
            ("stream_event_id", "session_id", "occurred_at", "event_type",
             "attempt", "delay_seconds"),
            (event_id, session_id, _time(occurred_at), event_type, attempt, delay_seconds),
            body,
        )

    def stream_cursor(self, session_id: str) -> dict[str, tuple[datetime, str]]:
        rows = self.repository.connection.execute(
            """SELECT symbol, provider_timestamp, raw_payload_hash
               FROM webull_stream_notifications
               WHERE session_id = ? AND symbol IS NOT NULL
                 AND provider_timestamp IS NOT NULL
               ORDER BY provider_timestamp, notification_id""",
            (session_id,),
        ).fetchall()
        cursor: dict[str, tuple[datetime, str]] = {}
        for symbol, provider_timestamp, payload_hash in rows:
            cursor[str(symbol)] = (
                datetime.fromisoformat(str(provider_timestamp).replace("Z", "+00:00"))
                .astimezone(UTC),
                str(payload_hash),
            )
        return cursor

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
                       order: WebullStockOrder, response: WebullResponse,
                       *, accepted: bool) -> str:
        request_hash = canonical_hash(order)
        preview_id = deterministic_id("webull_preview", (session_id, intent_id, request_hash))
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
        return self.preview_status(session_id, intent_id, request_hash) is True

    def preview_status(
        self, session_id: str, intent_id: str, request_hash: str
    ) -> bool | None:
        row = self.repository.connection.execute(
            """SELECT accepted FROM webull_order_previews
               WHERE session_id = ? AND intent_id = ? AND request_hash = ?""",
            (session_id, intent_id, request_hash),
        ).fetchone()
        if row is None:
            return None
        value = row[0]
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError("stored Webull preview status is invalid")
        return bool(value)

    def insert_mapping(self, session_id: str, intent_id: str,
                       order: WebullStockOrder, response: WebullResponse) -> bool:
        request_hash = canonical_hash(order)
        mapping_id = deterministic_id("webull_mapping", (session_id, intent_id))
        broker_order_id = response.payload.get("order_id")
        response_order = response.payload.get("order")
        if broker_order_id is None and isinstance(response_order, dict):
            broker_order_id = response_order.get("order_id")
        broker_id = str(broker_order_id) if broker_order_id is not None else None
        redacted_response = redact(response.payload)
        if not isinstance(redacted_response, dict):
            raise TypeError("redacted Webull mapping response must remain a mapping")
        payload = {"mapping_id": mapping_id, "session_id": session_id, "intent_id": intent_id,
                   "client_order_id": order.client_order_id, "request_hash": request_hash,
                   "broker_order_id": broker_id,
                   "response": WebullResponse(response.status_code, redacted_response)}
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

    def mappings(self, session_id: str) -> tuple[tuple[str, str, str, str | None], ...]:
        rows = self.repository.connection.execute(
            """SELECT intent_id, client_order_id, request_hash, broker_order_id
               FROM webull_client_orders WHERE session_id = ?
               ORDER BY client_order_id""",
            (session_id,),
        ).fetchall()
        return tuple(
            (str(intent_id), str(client_order_id), str(request_hash),
             None if broker_order_id is None else str(broker_order_id))
            for intent_id, client_order_id, request_hash, broker_order_id in rows
        )

    def mapping_for_intent(
        self, session_id: str, intent_id: str, request_hash: str
    ) -> tuple[str, str | None] | None:
        row = self.repository.connection.execute(
            """SELECT client_order_id, broker_order_id FROM webull_client_orders
               WHERE session_id = ? AND intent_id = ? AND request_hash = ?""",
            (session_id, intent_id, request_hash),
        ).fetchone()
        if row is None:
            return None
        return str(row[0]), None if row[1] is None else str(row[1])

    def unresolved_submission_intents(self, session_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT s.intent_id FROM webull_submission_events s
               LEFT JOIN webull_client_orders m
                 ON m.session_id = s.session_id AND m.intent_id = s.intent_id
               WHERE s.session_id = ? AND m.intent_id IS NULL
                 AND s.rowid = (
                     SELECT MAX(latest.rowid) FROM webull_submission_events latest
                     WHERE latest.session_id = s.session_id
                       AND latest.intent_id = s.intent_id
                 )
                 AND s.event_type != 'NOT_SUBMITTED'
               ORDER BY s.intent_id""",
            (session_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def insert_submission_event(
        self,
        session_id: str,
        intent_id: str,
        order: WebullStockOrder,
        occurred_at: datetime,
        event_type: WebullSubmissionEventType,
        detail: object = (),
    ) -> bool:
        request_hash = canonical_hash(order)
        event_id = deterministic_id(
            "webull_submission_event",
            (session_id, intent_id, request_hash, occurred_at, event_type, detail),
        )
        payload = {
            "submission_event_id": event_id,
            "session_id": session_id,
            "intent_id": intent_id,
            "client_order_id": order.client_order_id,
            "request_hash": request_hash,
            "occurred_at": occurred_at,
            "event_type": event_type,
            "detail": detail,
        }
        return self._insert(
            "webull_submission_events",
            "submission_event_id",
            event_id,
            (
                "submission_event_id",
                "session_id",
                "intent_id",
                "client_order_id",
                "request_hash",
                "occurred_at",
                "event_type",
            ),
            (
                event_id,
                session_id,
                intent_id,
                order.client_order_id,
                request_hash,
                _time(occurred_at),
                event_type.value,
            ),
            payload,
        )

    def insert_entry_release(self, item: WebullEntryRelease) -> bool:
        return self._insert(
            "webull_entry_releases",
            "release_id",
            item.release_id,
            (
                "release_id",
                "session_id",
                "intent_id",
                "request_hash",
                "provider_timestamp",
                "received_at",
                "approved",
                "reason",
            ),
            (
                item.release_id,
                item.session_id,
                item.intent_id,
                item.request_hash,
                _time(item.provider_timestamp),
                _time(item.received_at),
                int(item.approved),
                item.reason,
            ),
            item,
        )

    def entry_release_status(
        self, session_id: str, intent_id: str, request_hash: str
    ) -> tuple[datetime, bool] | None:
        row = self.repository.connection.execute(
            """SELECT received_at, approved FROM webull_entry_releases
               WHERE session_id = ? AND intent_id = ? AND request_hash = ?""",
            (session_id, intent_id, request_hash),
        ).fetchone()
        if row is None:
            return None
        value = row[1]
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError("stored Webull entry release status is invalid")
        return datetime.fromisoformat(str(row[0])).astimezone(UTC), bool(value)

    def entry_release_approved(
        self, session_id: str, intent_id: str, request_hash: str
    ) -> bool:
        status = self.entry_release_status(session_id, intent_id, request_hash)
        return status is not None and status[1]

    def submission_event_types(
        self, session_id: str, intent_id: str, request_hash: str
    ) -> tuple[WebullSubmissionEventType, ...]:
        rows = self.repository.connection.execute(
            """SELECT event_type FROM webull_submission_events
               WHERE session_id = ? AND intent_id = ? AND request_hash = ?
               ORDER BY occurred_at, rowid""",
            (session_id, intent_id, request_hash),
        ).fetchall()
        return tuple(WebullSubmissionEventType(str(row[0])) for row in rows)

    def insert_broker_event(
        self, session_id: str, occurred_at: datetime, item: WebullOrderSnapshot
    ) -> bool:
        event_id = deterministic_id(
            "webull_broker_event",
            (session_id, item.client_order_id, occurred_at, item.status, item.filled_quantity),
        )
        payload = {
            "broker_order_id": item.broker_order_id,
            "client_order_id": item.client_order_id,
            "symbol": item.symbol,
            "side": item.side,
            "quantity": item.quantity,
            "filled_quantity": item.filled_quantity,
            "status": item.status,
        }
        return self._insert(
            "webull_broker_events",
            "event_id",
            event_id,
            ("event_id", "session_id", "client_order_id", "occurred_at", "status"),
            (
                event_id,
                session_id,
                item.client_order_id,
                _time(occurred_at),
                item.status.value,
            ),
            payload,
        )

    def latest_broker_status(self, session_id: str, client_order_id: str) -> str | None:
        row = self.repository.connection.execute(
            """SELECT status FROM webull_broker_events
               WHERE session_id = ? AND client_order_id = ?
               ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (session_id, client_order_id),
        ).fetchone()
        return None if row is None else str(row[0])

    def insert_execution(
        self, session_id: str, occurred_at: datetime, item: WebullOrderSnapshot
    ) -> bool:
        if item.filled_quantity <= 0:
            return False
        execution_id = deterministic_id(
            "webull_execution",
            (session_id, item.client_order_id, item.filled_quantity),
        )
        payload = {
            "execution_id": execution_id,
            "client_order_id": item.client_order_id,
            "symbol": item.symbol,
            "side": item.side,
            "cumulative_quantity": item.filled_quantity,
        }
        return self._insert(
            "webull_executions",
            "execution_id",
            execution_id,
            (
                "execution_id",
                "session_id",
                "client_order_id",
                "occurred_at",
                "symbol",
                "side",
                "cumulative_quantity",
            ),
            (
                execution_id,
                session_id,
                item.client_order_id,
                _time(occurred_at),
                item.symbol,
                item.side.value,
                item.filled_quantity,
            ),
            payload,
        )

    def expected_positions(self, session_id: str) -> dict[str, int]:
        rows = self.repository.connection.execute(
            """SELECT symbol, side, cumulative_quantity, client_order_id
               FROM webull_executions WHERE session_id = ?
               ORDER BY occurred_at, rowid""",
            (session_id,),
        ).fetchall()
        latest: dict[str, tuple[str, str, int]] = {}
        for symbol, side, quantity, client_order_id in rows:
            latest[str(client_order_id)] = (str(symbol), str(side), int(quantity))
        result: dict[str, int] = {}
        for symbol, client_side, quantity in latest.values():
            signed = quantity if client_side == "BUY" else -quantity
            result[symbol] = result.get(symbol, 0) + signed
        return result

    def insert_reconciliation(self, item: WebullReconciliation) -> bool:
        return self._insert(
            "webull_reconciliations",
            "reconciliation_id",
            item.reconciliation_id,
            ("reconciliation_id", "session_id", "occurred_at", "matched"),
            (
                item.reconciliation_id,
                item.session_id,
                _time(item.occurred_at),
                int(item.matched),
            ),
            item,
        )

    def latest_reconciliation(self, session_id: str) -> tuple[datetime, bool] | None:
        row = self.repository.connection.execute(
            """SELECT occurred_at, matched FROM webull_reconciliations
               WHERE session_id = ? ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        matched = row[1]
        if isinstance(matched, bool) or not isinstance(matched, int) or matched not in (0, 1):
            raise ValueError("stored Webull reconciliation status is invalid")
        return (
            datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).astimezone(UTC),
            bool(matched),
        )

    def latest_order_activity(self, session_id: str) -> datetime | None:
        row = self.repository.connection.execute(
            """SELECT MAX(occurred_at) FROM (
                   SELECT occurred_at FROM webull_submission_events WHERE session_id = ?
                   UNION ALL
                   SELECT occurred_at FROM webull_broker_events WHERE session_id = ?
               )""",
            (session_id, session_id),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).astimezone(UTC)

    def insert_incident(
        self,
        session_id: str,
        occurred_at: datetime,
        reason: str,
        details: tuple[str, ...] = (),
    ) -> bool:
        incident_id = deterministic_id(
            "webull_transport_incident", (session_id, occurred_at, reason, details)
        )
        payload = {
            "incident_id": incident_id,
            "session_id": session_id,
            "occurred_at": occurred_at,
            "reason": reason,
            "details": details,
        }
        return self._insert(
            "webull_transport_incidents",
            "incident_id",
            incident_id,
            ("incident_id", "session_id", "occurred_at", "reason"),
            (incident_id, session_id, _time(occurred_at), reason),
            payload,
        )
