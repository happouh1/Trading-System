"""Read-only Phase 9I summaries of locally persisted paper operations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class LocalStatusConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LocalStatusConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class LocalOperationsStatus:
    status_id: str
    database_state: str
    session_id: str | None
    session_created_at: str | None
    runtime_state: str
    operator_health: str
    health_observed_at: str | None
    intent_count: int
    incident_count: int
    unmatched_reconciliation_count: int
    latest_heartbeat_at: str | None
    latest_checkpoint_at: str | None
    reason_codes: tuple[str, ...]
    source_hash: str
    config_hash: str
    status_version: str = "9I.1.0"
    database_write_performed: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    scheduler_started: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.status_id
            or self.database_state not in {"AVAILABLE", "MISSING", "SCHEMA_MISSING"}
            or self.runtime_state not in {
                "UNKNOWN", "CREATED", "STARTING", "SHADOW", "PAPER_ENABLED",
                "DRAINING", "STOPPED", "HALTED",
            }
            or self.operator_health not in {"HEALTHY", "ATTENTION", "HALTED", "UNAVAILABLE"}
            or min(self.intent_count, self.incident_count, self.unmatched_reconciliation_count) < 0
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not self.source_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.status_version != "9I.1.0"
            or any((
                self.database_write_performed,
                self.network_used,
                self.credentials_loaded,
                self.broker_write_performed,
                self.scheduler_started,
                self.sandbox_execution_enabled,
                self.live_trading_enabled,
            ))
        ):
            raise ValueError("invalid Phase 9I local operations status")


def load_local_status_config(path: str | Path) -> LocalStatusConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "status_version", "mode", "dashboard_config", "database",
        "session_selection", "authority",
    }:
        raise LocalStatusConfigError("Phase 9I configuration keys are invalid")
    if (
        raw["status_version"] != "9I.1.0"
        or raw["mode"] != "OFFLINE_LOCAL_STATUS"
        or raw["session_selection"] != "LATEST_CREATED"
    ):
        raise LocalStatusConfigError("Phase 9I mode is invalid")
    if not _canonical_relative_path(raw["dashboard_config"]):
        raise LocalStatusConfigError("Phase 9I dashboard path is invalid")
    if (
        not _canonical_relative_path(raw["database"])
        or not str(raw["database"]).endswith(".sqlite")
    ):
        raise LocalStatusConfigError("Phase 9I database path is invalid")
    authority = raw["authority"]
    expected = {
        "database_write_enabled", "process_scheduler_enabled", "network_enabled",
        "credential_loading_enabled", "broker_writes_enabled", "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected
        or any(value is not False for value in authority.values())
    ):
        raise LocalStatusConfigError("Phase 9I authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return LocalStatusConfig(MappingProxyType(frozen), canonical_hash(raw))


def inspect_local_operations(
    config: LocalStatusConfig, *, project_root: str | Path
) -> LocalOperationsStatus:
    root = Path(project_root).resolve()
    database_value = config.values["database"]
    if not isinstance(database_value, str):
        raise TypeError("validated Phase 9I database path must be text")
    database = (root / database_value).resolve()
    if root not in database.parents:
        raise LocalStatusConfigError("Phase 9I database escapes the project root")
    if not database.is_file():
        return _status(config, "MISSING", None, reasons=("DATABASE_MISSING",))
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        required = {
            "paper_sessions", "paper_transitions", "paper_intents", "paper_incidents",
            "paper_reconciliations", "paper_heartbeats", "paper_checkpoints",
        }
        if not required.issubset(tables):
            return _status(config, "SCHEMA_MISSING", None, reasons=("DATABASE_SCHEMA_MISSING",))
        row = connection.execute(
            "SELECT session_id, created_at FROM paper_sessions "
            "ORDER BY created_at DESC, session_id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return _status(config, "AVAILABLE", None, reasons=("PAPER_SESSION_MISSING",))
        return _session_status(
            config,
            connection,
            str(row[0]),
            str(row[1]),
            operator_snapshots_available="paper_operator_snapshots" in tables,
        )
    finally:
        connection.close()


def _session_status(
    config: LocalStatusConfig,
    connection: sqlite3.Connection,
    session_id: str,
    created_at: str,
    *,
    operator_snapshots_available: bool,
) -> LocalOperationsStatus:
    transition = connection.execute(
        "SELECT new_state FROM paper_transitions WHERE session_id=? "
        "ORDER BY occurred_at DESC, transition_id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    runtime_state = "CREATED" if transition is None else str(transition[0])
    intent_count = _count(connection, "paper_intents", session_id)
    incident_count = _count(connection, "paper_incidents", session_id)
    unmatched = int(connection.execute(
        "SELECT COUNT(*) FROM paper_reconciliations WHERE session_id=? AND matched=0",
        (session_id,),
    ).fetchone()[0])
    heartbeat = _latest(connection, "paper_heartbeats", "occurred_at", session_id)
    checkpoint = _latest(connection, "paper_checkpoints", "known_at", session_id)
    snapshot = None
    if operator_snapshots_available:
        snapshot = connection.execute(
            "SELECT observed_at, health, payload_json, payload_hash "
            "FROM paper_operator_snapshots WHERE session_id=? "
            "ORDER BY observed_at DESC, snapshot_id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    reasons: set[str] = set()
    health = "UNAVAILABLE"
    health_at: str | None = None
    if snapshot is None:
        reasons.add("OPERATOR_SNAPSHOT_MISSING")
    else:
        payload = json.loads(str(snapshot[2]))
        if canonical_hash(payload) != str(snapshot[3]):
            raise ValueError("Phase 9I operator snapshot hash mismatch")
        health_at, health = str(snapshot[0]), str(snapshot[1])
        payload_reasons = payload.get("reason_codes") if isinstance(payload, dict) else None
        if isinstance(payload_reasons, list):
            reasons.update(str(item) for item in payload_reasons)
    values = (
        session_id, created_at, runtime_state, health, health_at, intent_count, incident_count,
        unmatched, heartbeat, checkpoint, tuple(sorted(reasons)),
    )
    return _status(
        config,
        "AVAILABLE",
        values,
        reasons=tuple(sorted(reasons)),
    )


def _status(
    config: LocalStatusConfig,
    database_state: str,
    values: tuple[object, ...] | None,
    *,
    reasons: tuple[str, ...],
) -> LocalOperationsStatus:
    if values is None:
        values = (None, None, "UNKNOWN", "UNAVAILABLE", None, 0, 0, 0, None, None, reasons)
    source_hash = canonical_hash((database_state, values, config.config_hash))
    identity = (database_state, values, source_hash, config.config_hash)
    return LocalOperationsStatus(
        deterministic_id("local_operations_status", identity),
        database_state,
        values[0] if isinstance(values[0], str) else None,
        values[1] if isinstance(values[1], str) else None,
        str(values[2]),
        str(values[3]),
        values[4] if isinstance(values[4], str) else None,
        _as_int(values[5]),
        _as_int(values[6]),
        _as_int(values[7]),
        values[8] if isinstance(values[8], str) else None,
        values[9] if isinstance(values[9], str) else None,
        reasons,
        source_hash,
        config.config_hash,
    )


def _count(connection: sqlite3.Connection, table: str, session_id: str) -> int:
    return int(connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE session_id=?", (session_id,)
    ).fetchone()[0])


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("validated Phase 9I count must be an integer")
    return value


def _latest(
    connection: sqlite3.Connection, table: str, column: str, session_id: str
) -> str | None:
    row = connection.execute(
        f"SELECT {column} FROM {table} WHERE session_id=? ORDER BY {column} DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return None if row is None else str(row[0])


def _canonical_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts
