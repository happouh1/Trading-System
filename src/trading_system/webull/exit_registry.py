"""Append-only Phase 3D sandbox exit persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from trading_system.domain import Direction
from trading_system.persistence import SQLiteRepository
from trading_system.webull.exit_contracts import (
    BrokerActionEvent,
    BrokerActionEventType,
    BrokerActionKind,
    ExitAuthorization,
    ExitIntent,
    FlattenAuthorization,
    ManagedPosition,
    PositionEvent,
    PositionLifecycleState,
    PositionReconciliation,
    ProtectiveStopVersion,
)
from trading_system.webull.registry import WebullRegistry


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Phase 3D registry timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


class WebullExitRegistry(WebullRegistry):
    def __init__(self, repository: SQLiteRepository) -> None:
        super().__init__(repository)

    def insert_managed_position(self, item: ManagedPosition) -> bool:
        return self._insert(
            "webull_managed_positions", "managed_position_id", item.managed_position_id,
            (
                "managed_position_id", "session_id", "entry_intent_id",
                "entry_client_order_id", "entry_broker_order_id", "symbol", "direction",
                "filled_quantity", "remaining_quantity", "entry_price",
                "initial_stop_adjusted", "opened_at", "config_hash", "code_version",
            ),
            (
                item.managed_position_id, item.session_id, item.entry_intent_id,
                item.entry_client_order_id, item.entry_broker_order_id, item.symbol,
                item.direction.value, item.filled_quantity, item.remaining_quantity,
                format(item.entry_price, "f"), format(item.initial_stop_adjusted, "f"),
                _time(item.opened_at), item.config_hash, item.code_version,
            ),
            item,
        )

    def managed_position(self, managed_position_id: str) -> ManagedPosition:
        row = self.repository.connection.execute(
            """SELECT managed_position_id, session_id, entry_intent_id,
                      entry_client_order_id, entry_broker_order_id, symbol, direction,
                      filled_quantity, remaining_quantity, entry_price,
                      initial_stop_adjusted, opened_at, config_hash, code_version
               FROM webull_managed_positions WHERE managed_position_id = ?""",
            (managed_position_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown managed position: {managed_position_id}")
        return ManagedPosition(
            managed_position_id=str(row[0]), session_id=str(row[1]),
            entry_intent_id=str(row[2]), entry_client_order_id=str(row[3]),
            entry_broker_order_id=str(row[4]), symbol=str(row[5]),
            direction=Direction(str(row[6])), filled_quantity=int(row[7]),
            remaining_quantity=int(row[8]), entry_price=Decimal(str(row[9])),
            initial_stop_adjusted=Decimal(str(row[10])), opened_at=_datetime(row[11]),
            config_hash=str(row[12]), code_version=str(row[13]),
        )

    def positions(self, session_id: str) -> tuple[ManagedPosition, ...]:
        rows = self.repository.connection.execute(
            """SELECT managed_position_id FROM webull_managed_positions
               WHERE session_id = ? ORDER BY managed_position_id""",
            (session_id,),
        ).fetchall()
        return tuple(self.managed_position(str(row[0])) for row in rows)

    def insert_position_event(self, item: PositionEvent) -> bool:
        return self._insert(
            "webull_position_events", "position_event_id", item.position_event_id,
            (
                "position_event_id", "managed_position_id", "session_id", "occurred_at",
                "state", "remaining_quantity", "reason", "evidence_hash",
            ),
            (
                item.position_event_id, item.managed_position_id, item.session_id,
                _time(item.occurred_at), item.state.value, item.remaining_quantity,
                item.reason, item.evidence_hash,
            ),
            item,
        )

    def latest_position_event(self, managed_position_id: str) -> PositionEvent | None:
        row = self.repository.connection.execute(
            """SELECT position_event_id, managed_position_id, session_id, occurred_at,
                      state, remaining_quantity, reason, evidence_hash
               FROM webull_position_events WHERE managed_position_id = ?
               ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (managed_position_id,),
        ).fetchone()
        if row is None:
            return None
        return PositionEvent(
            str(row[0]), str(row[1]), str(row[2]), _datetime(row[3]),
            PositionLifecycleState(str(row[4])), int(row[5]), str(row[6]), str(row[7]),
        )

    def insert_exit_intent(self, item: ExitIntent) -> bool:
        return self._insert(
            "webull_exit_intents", "exit_intent_id", item.exit_intent_id,
            (
                "exit_intent_id", "managed_position_id", "session_id", "reason",
                "signal_candle_id", "known_at", "scheduled_open", "requested_quantity",
                "evidence_hash",
            ),
            (
                item.exit_intent_id, item.managed_position_id, item.session_id,
                item.reason.value, item.signal_candle_id, _time(item.known_at),
                _time(item.scheduled_open), item.requested_quantity, item.evidence_hash,
            ),
            item,
        )

    def insert_stop_version(self, item: ProtectiveStopVersion) -> bool:
        return self._insert(
            "webull_protective_stop_versions", "stop_version_id", item.stop_version_id,
            (
                "stop_version_id", "managed_position_id", "session_id", "client_order_id",
                "known_at", "quantity", "adjusted_stop", "adjustment_factor", "raw_stop",
                "tick_size", "source_candle_id", "source_revision", "request_hash",
            ),
            (
                item.stop_version_id, item.managed_position_id, item.session_id,
                item.client_order_id, _time(item.known_at), item.quantity,
                format(item.adjusted_stop, "f"), format(item.adjustment_factor, "f"),
                format(item.raw_stop, "f"), format(item.tick_size, "f"),
                item.source_candle_id, item.source_revision, item.request_hash,
            ),
            item,
        )

    def latest_stop(self, managed_position_id: str) -> ProtectiveStopVersion | None:
        row = self.repository.connection.execute(
            """SELECT stop_version_id, session_id, managed_position_id, client_order_id,
                      known_at, quantity, adjusted_stop, adjustment_factor, raw_stop,
                      tick_size, source_candle_id, source_revision, request_hash
               FROM webull_protective_stop_versions WHERE managed_position_id = ?
               ORDER BY known_at DESC, rowid DESC LIMIT 1""",
            (managed_position_id,),
        ).fetchone()
        if row is None:
            return None
        return ProtectiveStopVersion(
            stop_version_id=str(row[0]), session_id=str(row[1]),
            managed_position_id=str(row[2]), client_order_id=str(row[3]),
            known_at=_datetime(row[4]), quantity=int(row[5]),
            adjusted_stop=Decimal(str(row[6])), adjustment_factor=Decimal(str(row[7])),
            raw_stop=Decimal(str(row[8])), tick_size=Decimal(str(row[9])),
            source_candle_id=str(row[10]), source_revision=str(row[11]),
            request_hash=str(row[12]),
        )

    def insert_action_event(self, item: BrokerActionEvent) -> bool:
        return self._insert(
            "webull_broker_action_events", "broker_action_id", item.broker_action_id,
            (
                "broker_action_id", "managed_position_id", "session_id", "action_kind",
                "event_type", "client_order_id", "request_hash", "occurred_at",
            ),
            (
                item.broker_action_id, item.managed_position_id, item.session_id,
                item.action_kind.value, item.event_type.value, item.client_order_id,
                item.request_hash, _time(item.occurred_at),
            ),
            item,
        )

    def unresolved_actions(self, session_id: str) -> tuple[tuple[str, str, str, str], ...]:
        rows = self.repository.connection.execute(
            """SELECT managed_position_id, action_kind, client_order_id, request_hash
               FROM webull_broker_action_events current
               WHERE session_id = ?
                 AND rowid = (
                    SELECT MAX(latest.rowid) FROM webull_broker_action_events latest
                    WHERE latest.session_id = current.session_id
                      AND latest.managed_position_id = current.managed_position_id
                      AND latest.action_kind = current.action_kind
                      AND latest.client_order_id = current.client_order_id
                 )
                 AND event_type IN ('PREPARED', 'CALL_STARTED', 'AMBIGUOUS')
               ORDER BY managed_position_id, client_order_id""",
            (session_id,),
        ).fetchall()
        return tuple(
            (str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in rows
        )

    def insert_exit_authorization(self, item: ExitAuthorization) -> bool:
        return self._insert(
            "webull_exit_authorizations", "authorization_id", item.authorization_id,
            (
                "authorization_id", "session_id", "config_hash", "capability_hash",
                "reconciliation_id", "created_at", "expires_at",
            ),
            (
                item.authorization_id, item.session_id, item.config_hash,
                item.capability_hash, item.reconciliation_id, _time(item.created_at),
                _time(item.expires_at),
            ),
            item,
        )

    def latest_account_reconciliation(
        self, session_id: str
    ) -> tuple[str, datetime, bool] | None:
        row = self.repository.connection.execute(
            """SELECT reconciliation_id, occurred_at, matched
               FROM webull_reconciliations WHERE session_id = ?
               ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        value = row[2]
        if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
            raise ValueError("stored Webull reconciliation status is invalid")
        return str(row[0]), _datetime(row[1]), bool(value)

    def valid_exit_authorization(
        self, session_id: str, config_hash: str, capability_hash: str, at: datetime
    ) -> bool:
        row = self.repository.connection.execute(
            """SELECT 1 FROM webull_exit_authorizations
               WHERE session_id = ? AND config_hash = ? AND capability_hash = ?
                 AND created_at <= ? AND expires_at >= ? LIMIT 1""",
            (session_id, config_hash, capability_hash, _time(at), _time(at)),
        ).fetchone()
        if row is None:
            return False
        value = row[0]
        return isinstance(value, int) and not isinstance(value, bool) and value == 1

    def insert_flatten_authorization(self, item: FlattenAuthorization) -> bool:
        return self._insert(
            "webull_flatten_authorizations", "flatten_auth_id", item.flatten_auth_id,
            (
                "flatten_auth_id", "managed_position_id", "session_id",
                "reconciliation_id", "symbol", "direction", "created_at", "used_at",
            ),
            (
                item.flatten_auth_id, item.managed_position_id, item.session_id,
                item.reconciliation_id, item.symbol, item.direction.value,
                _time(item.created_at), None if item.used_at is None else _time(item.used_at),
            ),
            item,
        )

    def flatten_consumed(self, flatten_auth_id: str) -> bool:
        row = self.repository.connection.execute(
            """SELECT 1 FROM webull_broker_action_events
               WHERE event_type = 'CALL_STARTED' AND payload_json LIKE ? LIMIT 1""",
            (f'%"flatten_auth_id":"{flatten_auth_id}"%',),
        ).fetchone()
        if row is None:
            return False
        value = row[0]
        return isinstance(value, int) and not isinstance(value, bool) and value == 1

    def insert_position_reconciliation(self, item: PositionReconciliation) -> bool:
        return self._insert(
            "webull_position_reconciliations", "reconciliation_id", item.reconciliation_id,
            (
                "reconciliation_id", "managed_position_id", "session_id", "occurred_at",
                "expected_quantity", "actual_quantity", "matched",
            ),
            (
                item.reconciliation_id, item.managed_position_id, item.session_id,
                _time(item.occurred_at), item.expected_quantity, item.actual_quantity,
                int(item.matched),
            ),
            item,
        )

    def latest_position_reconciliation(
        self, managed_position_id: str
    ) -> PositionReconciliation | None:
        row = self.repository.connection.execute(
            """SELECT reconciliation_id, session_id, managed_position_id, occurred_at,
                      expected_quantity, actual_quantity, matched
               FROM webull_position_reconciliations WHERE managed_position_id = ?
               ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (managed_position_id,),
        ).fetchone()
        if row is None:
            return None
        matched = int(row[6]) == 1
        differences = () if matched else ("POSITION_QUANTITY_MISMATCH",)
        return PositionReconciliation(
            str(row[0]), str(row[1]), str(row[2]), _datetime(row[3]), int(row[4]),
            int(row[5]), matched, differences,
        )

    def action_types(
        self, managed_position_id: str, client_order_id: str
    ) -> tuple[BrokerActionEventType, ...]:
        rows = self.repository.connection.execute(
            """SELECT event_type FROM webull_broker_action_events
               WHERE managed_position_id = ? AND client_order_id = ?
               ORDER BY occurred_at, rowid""",
            (managed_position_id, client_order_id),
        ).fetchall()
        return tuple(BrokerActionEventType(str(row[0])) for row in rows)

    def latest_execution_quantity(self, session_id: str, client_order_id: str) -> int:
        row = self.repository.connection.execute(
            """SELECT MAX(cumulative_quantity) FROM webull_executions
               WHERE session_id = ? AND client_order_id = ?""",
            (session_id, client_order_id),
        ).fetchone()
        if row is None or row[0] is None:
            return 0
        value = row[0]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("stored cumulative Webull execution quantity is invalid")
        return int(value)

    def latest_action_kind(self, managed_position_id: str) -> BrokerActionKind | None:
        row = self.repository.connection.execute(
            """SELECT action_kind FROM webull_broker_action_events
               WHERE managed_position_id = ? ORDER BY occurred_at DESC, rowid DESC LIMIT 1""",
            (managed_position_id,),
        ).fetchone()
        return None if row is None else BrokerActionKind(str(row[0]))
