"""Append-only Phase 5D controls with derived fail-closed state."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.operations.control_config import OperationsControlConfig
from trading_system.operations.controls import (
    ApprovalAction,
    ApprovalEvent,
    CancellationAction,
    CancellationEvent,
    ControlSnapshot,
    ControlStatus,
    IncidentAction,
    IncidentEvent,
    IncidentState,
    KillSwitchEvent,
    SwitchAction,
)
from trading_system.operations.runner import JobRunRequest
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class OperationsControlRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: OperationsControlConfig,
    ) -> None:
        self.repository = repository
        self.config = config

    def _exists(self, table: str, column: str, identity: str) -> bool:
        allowed = {
            ("operations_run_requests", "request_id"),
            ("operations_internal_alerts", "alert_id"),
        }
        if (table, column) not in allowed:
            raise ValueError("unsupported control reference")
        return (
            self.repository.connection.execute(
                f"SELECT 1 FROM {table} WHERE {column} = ?", (identity,)
            ).fetchone()
            is not None
        )

    def insert_approval(self, event: ApprovalEvent) -> bool:
        if event.config_hash != self.config.config_hash:
            raise ValueError("approval configuration hash mismatch")
        if not self._exists("operations_run_requests", "request_id", event.request_id):
            raise ValueError("approval references an unknown run request")
        latest = self.repository.connection.execute(
            """SELECT action FROM operations_approval_events
               WHERE request_id = ? AND operator_id = ?
               ORDER BY known_at DESC, event_id DESC LIMIT 1""",
            (event.request_id, event.operator_id),
        ).fetchone()
        if event.action is ApprovalAction.REVOKE and (
            latest is None or str(latest[0]) != ApprovalAction.GRANT.value
        ):
            raise ValueError("approval revocation requires an active latest grant")
        return self._insert(
            "operations_approval_events",
            event.event_id,
            (
                "request_id",
                "operator_id",
                "action",
                "known_at",
                "expires_at",
                "config_hash",
            ),
            (
                event.request_id,
                event.operator_id,
                event.action.value,
                _time(event.known_at),
                None if event.expires_at is None else _time(event.expires_at),
                event.config_hash,
            ),
            event,
        )

    def insert_kill_switch(self, event: KillSwitchEvent) -> bool:
        if event.config_hash != self.config.config_hash:
            raise ValueError("kill switch configuration hash mismatch")
        return self._insert(
            "operations_kill_switch_events",
            event.event_id,
            ("component", "action", "known_at", "operator_id", "config_hash"),
            (
                event.component,
                event.action.value,
                _time(event.known_at),
                event.operator_id,
                event.config_hash,
            ),
            event,
        )

    def insert_cancellation(self, event: CancellationEvent) -> bool:
        if event.config_hash != self.config.config_hash:
            raise ValueError("cancellation configuration hash mismatch")
        if not self._exists("operations_run_requests", "request_id", event.request_id):
            raise ValueError("cancellation references an unknown run request")
        latest = self.repository.connection.execute(
            """SELECT action FROM operations_cancellation_events WHERE request_id = ?
               ORDER BY known_at DESC, event_id DESC LIMIT 1""",
            (event.request_id,),
        ).fetchone()
        if event.action is CancellationAction.CLEAR and (
            latest is None or str(latest[0]) != CancellationAction.REQUEST.value
        ):
            raise ValueError("cancellation clear requires an active request")
        return self._insert(
            "operations_cancellation_events",
            event.event_id,
            ("request_id", "action", "known_at", "operator_id", "config_hash"),
            (
                event.request_id,
                event.action.value,
                _time(event.known_at),
                event.operator_id,
                event.config_hash,
            ),
            event,
        )

    def insert_incident(self, event: IncidentEvent) -> bool:
        if event.config_hash != self.config.config_hash:
            raise ValueError("incident configuration hash mismatch")
        if not self._exists("operations_internal_alerts", "alert_id", event.alert_id):
            raise ValueError("incident references an unknown alert")
        latest = self.repository.connection.execute(
            """SELECT action FROM operations_incident_events WHERE alert_id = ?
               ORDER BY known_at DESC, event_id DESC LIMIT 1""",
            (event.alert_id,),
        ).fetchone()
        state = IncidentState.OPEN
        if latest is not None:
            action = IncidentAction(str(latest[0]))
            state = {
                IncidentAction.ACKNOWLEDGE: IncidentState.ACKNOWLEDGED,
                IncidentAction.RESOLVE: IncidentState.RESOLVED,
                IncidentAction.REOPEN: IncidentState.OPEN,
            }[action]
        expected = {
            IncidentState.OPEN: IncidentAction.ACKNOWLEDGE,
            IncidentState.ACKNOWLEDGED: IncidentAction.RESOLVE,
            IncidentState.RESOLVED: IncidentAction.REOPEN,
        }[state]
        if event.action is not expected:
            raise ValueError(f"incident transition requires {expected.value}")
        return self._insert(
            "operations_incident_events",
            event.event_id,
            ("alert_id", "action", "known_at", "operator_id", "config_hash"),
            (
                event.alert_id,
                event.action.value,
                _time(event.known_at),
                event.operator_id,
                event.config_hash,
            ),
            event,
        )

    def _latest_switches(self, as_of: datetime) -> tuple[bool, tuple[str, ...]]:
        rows = self.repository.connection.execute(
            """SELECT component, action FROM operations_kill_switch_events
               WHERE known_at <= ? ORDER BY known_at, event_id""",
            (_time(as_of),),
        ).fetchall()
        global_engaged = self.config.default_global_engaged
        components: dict[str, bool] = {}
        for component, action in rows:
            engaged = str(action) == SwitchAction.ENGAGE.value
            if component is None:
                global_engaged = engaged
            else:
                components[str(component)] = engaged
        return global_engaged, tuple(sorted(key for key, value in components.items() if value))

    def _active_operators(self, request_id: str, as_of: datetime) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT operator_id, action, expires_at FROM operations_approval_events
               WHERE request_id = ? AND known_at <= ? ORDER BY known_at, event_id""",
            (request_id, _time(as_of)),
        ).fetchall()
        latest: dict[str, tuple[str, str | None]] = {}
        for operator, action, expires in rows:
            latest[str(operator)] = (str(action), None if expires is None else str(expires))
        now = _time(as_of)
        return tuple(
            sorted(
                operator
                for operator, (action, expires) in latest.items()
                if action == ApprovalAction.GRANT.value and expires is not None and expires > now
            )
        )

    def _cancelled(self, request_id: str, as_of: datetime) -> bool:
        row = self.repository.connection.execute(
            """SELECT action FROM operations_cancellation_events
               WHERE request_id = ? AND known_at <= ?
               ORDER BY known_at DESC, event_id DESC LIMIT 1""",
            (request_id, _time(as_of)),
        ).fetchone()
        return row is not None and str(row[0]) == CancellationAction.REQUEST.value

    def _incident_states(
        self, as_of: datetime
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        alerts = self.repository.connection.execute(
            "SELECT alert_id FROM operations_internal_alerts WHERE known_at <= ? ORDER BY alert_id",
            (_time(as_of),),
        ).fetchall()
        rows = self.repository.connection.execute(
            """SELECT alert_id, action FROM operations_incident_events
               WHERE known_at <= ? ORDER BY known_at, event_id""",
            (_time(as_of),),
        ).fetchall()
        latest = {str(alert): IncidentAction(str(action)) for alert, action in rows}
        open_ids: list[str] = []
        acknowledged: list[str] = []
        resolved: list[str] = []
        for row in alerts:
            alert_id = str(row[0])
            action = latest.get(alert_id)
            if action is IncidentAction.ACKNOWLEDGE:
                acknowledged.append(alert_id)
            elif action is IncidentAction.RESOLVE:
                resolved.append(alert_id)
            else:
                open_ids.append(alert_id)
        return tuple(open_ids), tuple(acknowledged), tuple(resolved)

    def snapshot(self, *, as_of: datetime, request_id: str | None) -> ControlSnapshot:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("control as_of must be timezone-aware")
        global_engaged, component_kills = self._latest_switches(as_of)
        active_operators: tuple[str, ...] = ()
        cancelled = False
        request_component = None
        if request_id is not None:
            row = self.repository.connection.execute(
                """SELECT schedules.component FROM operations_run_requests AS requests
                   JOIN operations_schedules AS schedules
                     ON schedules.job_id = requests.schedule_job_id
                   WHERE requests.request_id = ?""",
                (request_id,),
            ).fetchone()
            if row is None:
                raise ValueError("control snapshot references an unknown request")
            request_component = str(row[0])
            active_operators = self._active_operators(request_id, as_of)
            cancelled = self._cancelled(request_id, as_of)
        open_ids, acknowledged, resolved = self._incident_states(as_of)
        reasons: list[str] = []
        if global_engaged:
            reasons.append("GLOBAL_KILL_ENGAGED")
        if request_component is not None and request_component in component_kills:
            reasons.append(f"COMPONENT_KILL_ENGAGED:{request_component}")
        if (
            request_id is not None
            and len(active_operators) < self.config.required_distinct_operators
        ):
            reasons.append(
                f"APPROVALS_ACTIVE:{len(active_operators)}_REQUIRED:"
                f"{self.config.required_distinct_operators}"
            )
        if cancelled:
            reasons.append("CANCELLATION_REQUESTED")
        halted = bool(reasons)
        status = (
            ControlStatus.HALTED
            if halted
            else ControlStatus.ATTENTION
            if open_ids or acknowledged
            else ControlStatus.READY
        )
        return ControlSnapshot.create(
            as_of=as_of,
            request_id=request_id,
            status=status,
            global_kill_engaged=global_engaged,
            component_kills=component_kills,
            active_operators=active_operators,
            cancellation_requested=cancelled,
            open_alert_ids=open_ids,
            acknowledged_alert_ids=acknowledged,
            resolved_alert_ids=resolved,
            reasons=tuple(reasons),
            config_hash=self.config.config_hash,
        )

    def authorize(self, request: JobRunRequest, at: datetime) -> ControlSnapshot:
        snapshot = self.snapshot(as_of=at, request_id=request.request_id)
        self.insert_snapshot(snapshot)
        if snapshot.status is ControlStatus.HALTED:
            raise ValueError("controlled run halted: " + ",".join(snapshot.reasons))
        return snapshot

    def insert_snapshot(self, snapshot: ControlSnapshot) -> bool:
        return self._insert(
            "operations_control_snapshots",
            snapshot.snapshot_id,
            ("as_of", "request_id", "status", "config_hash"),
            (
                _time(snapshot.as_of),
                snapshot.request_id,
                snapshot.status.value,
                snapshot.config_hash,
            ),
            snapshot,
        )

    def _insert(
        self,
        table: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        allowed = {
            "operations_approval_events",
            "operations_kill_switch_events",
            "operations_cancellation_events",
            "operations_incident_events",
            "operations_control_snapshots",
        }
        if table not in allowed:
            raise ValueError("unsupported control table")
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        names: tuple[str, ...] = (
            "event_id" if table != "operations_control_snapshots" else "snapshot_id",
        )
        names += (*columns, "payload_json", "payload_hash")
        placeholders = ",".join("?" for _ in names)
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(names)}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            id_column = names[0]
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {id_column} = ?", (identity,)
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload")
            self.repository.connection.commit()
            return False
        self.repository.connection.commit()
        return True
