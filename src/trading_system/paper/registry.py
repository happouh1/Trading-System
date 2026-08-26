"""Append-only Phase 3B operational registry."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from trading_system.domain import Direction, Timeframe, TradePlan
from trading_system.paper.contracts import (
    AdapterResult,
    IntentStatus,
    OrderIntent,
    PaperSession,
    ReconciliationResult,
    RuntimeState,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("paper registry timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class PaperRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def _insert(self, table: str, identity_column: str, identity: str,
                columns: tuple[str, ...], values: tuple[object, ...], payload: object) -> bool:
        payload_json, payload_hash = canonical_json(payload), canonical_hash(payload)
        names = (*columns, "payload_json", "payload_hash")
        placeholders = ",".join("?" for _ in names)
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(names)}) VALUES ({placeholders})",
            (*values, payload_json, payload_hash),
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

    def insert_session(self, item: PaperSession) -> bool:
        return self._insert(
            "paper_sessions", "session_id", item.session_id,
            ("session_id", "created_at", "mode", "code_version", "config_hash",
             "data_revision", "calendar_version"),
            (item.session_id, _time(item.created_at), item.mode.value, item.code_version,
             item.config_hash, item.data_revision, item.calendar_version), item,
        )

    def session_payload(self, session_id: str) -> dict[str, object]:
        row = self.repository.connection.execute(
            "SELECT payload_json FROM paper_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown paper session: {session_id}")
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            raise ValueError("stored paper session is invalid")
        return {str(key): item for key, item in value.items()}

    def current_state(self, session_id: str) -> RuntimeState:
        self.session_payload(session_id)
        row = self.repository.connection.execute(
            """SELECT new_state FROM paper_transitions WHERE session_id = ?
               ORDER BY rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        return RuntimeState.CREATED if row is None else RuntimeState(str(row[0]))

    def transition(self, session_id: str, new_state: RuntimeState,
                   occurred_at: datetime, reason: str) -> bool:
        prior = self.current_state(session_id)
        allowed = {
            RuntimeState.CREATED: {RuntimeState.STARTING, RuntimeState.HALTED},
            RuntimeState.STARTING: {RuntimeState.SHADOW, RuntimeState.PAPER_ENABLED,
                                    RuntimeState.HALTED},
            RuntimeState.SHADOW: {
                RuntimeState.PAPER_ENABLED,
                RuntimeState.DRAINING,
                RuntimeState.HALTED,
            },
            RuntimeState.PAPER_ENABLED: {RuntimeState.DRAINING, RuntimeState.HALTED},
            RuntimeState.DRAINING: {RuntimeState.STOPPED, RuntimeState.HALTED},
            RuntimeState.HALTED: {RuntimeState.STARTING},
        }
        if new_state not in allowed.get(prior, set()):
            raise ValueError(f"invalid paper transition: {prior}->{new_state}")
        identity = (session_id, prior, new_state, reason)
        transition_id = deterministic_id("paper_transition", identity)
        payload = {"transition_id": transition_id, "session_id": session_id,
                   "prior_state": prior, "new_state": new_state,
                   "occurred_at": occurred_at, "reason": reason}
        return self._insert(
            "paper_transitions", "transition_id", transition_id,
            ("transition_id", "session_id", "prior_state", "new_state", "occurred_at", "reason"),
            (transition_id, session_id, prior.value, new_state.value, _time(occurred_at), reason),
            payload,
        )

    def insert_intent(self, item: OrderIntent) -> bool:
        return self._insert(
            "paper_intents", "intent_id", item.intent_id,
            ("intent_id", "session_id", "trade_plan_id", "scheduled_open", "status"),
            (item.intent_id, item.session_id, item.trade_plan_id,
             _time(item.scheduled_open), item.status.value), item,
        )

    def load_intent(self, intent_id: str) -> OrderIntent:
        row = self.repository.connection.execute(
            """SELECT session_id, trade_plan_id, scheduled_open, status, payload_json
               FROM paper_intents WHERE intent_id = ?""",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown paper intent: {intent_id}")
        payload = json.loads(str(row[4]))
        detail = payload.get("payload") if isinstance(payload, dict) else None
        plan_payload = detail.get("trade_plan") if isinstance(detail, dict) else None
        if not isinstance(plan_payload, dict):
            raise ValueError("stored paper intent has no trade plan")

        def tagged(value: object, tag: str) -> str:
            if not isinstance(value, dict) or set(value) != {tag}:
                raise ValueError(f"stored paper intent has invalid {tag} value")
            result = value[tag]
            if not isinstance(result, str):
                raise ValueError(f"stored paper intent has invalid {tag} value")
            return result

        plan = TradePlan(
            str(plan_payload["plan_id"]),
            str(plan_payload["symbol"]),
            Timeframe(str(plan_payload["timeframe"])),
            Direction(str(plan_payload["direction"])),
            datetime.fromisoformat(
                tagged(plan_payload["created_at"], "__datetime__").replace("Z", "+00:00")
            ).astimezone(UTC),
            Decimal(tagged(plan_payload["planned_entry"], "__decimal__")),
            Decimal(tagged(plan_payload["initial_stop"], "__decimal__")),
            Decimal(tagged(plan_payload["risk_per_unit"], "__decimal__")),
            None if plan_payload["runway_adr"] is None else Decimal(
                tagged(plan_payload["runway_adr"], "__decimal__")
            ),
            None if plan_payload["reward_risk"] is None else Decimal(
                tagged(plan_payload["reward_risk"], "__decimal__")
            ),
            str(plan_payload["pattern_instance_id"]),
        )
        if plan.plan_id != str(row[1]):
            raise ValueError("stored paper intent plan identity mismatch")
        scheduled_open = datetime.fromisoformat(str(row[2]).replace("Z", "+00:00")).astimezone(UTC)
        return OrderIntent(
            intent_id, str(row[0]), plan.plan_id, scheduled_open, plan.created_at,
            IntentStatus(str(row[3])), {"trade_plan": plan},
        )

    def intent_ids(self, session_id: str) -> tuple[str, ...]:
        self.session_payload(session_id)
        rows = self.repository.connection.execute(
            """SELECT intent_id FROM paper_intents WHERE session_id = ?
               ORDER BY scheduled_open, intent_id""",
            (session_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def insert_adapter_result(self, session_id: str, item: AdapterResult) -> bool:
        event_id = deterministic_id("paper_adapter_event", (session_id, item))
        return self._insert(
            "paper_adapter_events", "adapter_event_id", event_id,
            ("adapter_event_id", "session_id", "intent_id", "event_type", "occurred_at"),
            (event_id, session_id, item.intent_id, item.status.value, _time(item.occurred_at)),
            item,
        )

    def acknowledged_order_ids(self, session_id: str) -> frozenset[str]:
        rows = self.repository.connection.execute(
            "SELECT payload_json FROM paper_adapter_events WHERE session_id = ? AND event_type = ?",
            (session_id, "ACKNOWLEDGED"),
        ).fetchall()
        result: set[str] = set()
        for row in rows:
            payload = json.loads(str(row[0]))
            order_id = payload.get("adapter_order_id") if isinstance(payload, dict) else None
            if isinstance(order_id, str):
                result.add(order_id)
        return frozenset(result)

    def insert_reconciliation(self, item: ReconciliationResult) -> bool:
        return self._insert(
            "paper_reconciliations", "reconciliation_id", item.reconciliation_id,
            ("reconciliation_id", "session_id", "occurred_at", "matched"),
            (item.reconciliation_id, item.session_id,
             _time(item.occurred_at), int(item.matched)),
            item,
        )

    def insert_incident(self, session_id: str, occurred_at: datetime,
                        reason: str, details: tuple[str, ...] = ()) -> bool:
        incident_id = deterministic_id("paper_incident", (session_id, occurred_at, reason, details))
        payload = {"incident_id": incident_id, "session_id": session_id,
                   "occurred_at": occurred_at, "reason": reason, "details": details}
        return self._insert(
            "paper_incidents", "incident_id", incident_id,
            ("incident_id", "session_id", "occurred_at", "reason"),
            (incident_id, session_id, _time(occurred_at), reason), payload,
        )

    def insert_checkpoint(self, session_id: str, candle_id: str, timeframe: str,
                          known_at: datetime, state_hash: str, payload: object) -> bool:
        checkpoint_id = deterministic_id("paper_checkpoint", (session_id, known_at, state_hash))
        return self._insert(
            "paper_checkpoints", "checkpoint_id", checkpoint_id,
            ("checkpoint_id", "session_id", "candle_id", "timeframe", "known_at", "state_hash"),
            (checkpoint_id, session_id, candle_id, timeframe, _time(known_at), state_hash), payload,
        )

    def latest_checkpoint(self, session_id: str) -> tuple[datetime, str, str] | None:
        row = self.repository.connection.execute(
            """SELECT known_at, state_hash, timeframe FROM paper_checkpoints
               WHERE session_id = ? ORDER BY rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return (datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")),
                str(row[1]), str(row[2]))

    def insert_heartbeat(self, session_id: str, occurred_at: datetime) -> bool:
        state = self.current_state(session_id)
        heartbeat_id = deterministic_id("paper_heartbeat", (session_id, occurred_at, state))
        payload = {"heartbeat_id": heartbeat_id, "session_id": session_id,
                   "occurred_at": occurred_at, "state": state}
        return self._insert(
            "paper_heartbeats", "heartbeat_id", heartbeat_id,
            ("heartbeat_id", "session_id", "occurred_at", "state"),
            (heartbeat_id, session_id, _time(occurred_at), state.value), payload,
        )

    def insert_report(self, session_id: str, created_at: datetime, payload: object) -> bool:
        report_id = deterministic_id("paper_report", (session_id, created_at, payload))
        return self._insert(
            "paper_reports", "report_id", report_id,
            ("report_id", "session_id", "created_at"),
            (report_id, session_id, _time(created_at)), payload,
        )
