"""Phase 12L append-only lifecycle evidence for scheduled SHADOW operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.paper.prospective_shadow_audit import (
    load_prospective_shadow_audit_config,
)
from trading_system.paper.prospective_shadow_orchestrator import (
    ProspectiveShadowScheduleConfig,
    load_prospective_shadow_schedule,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

OPERATIONS = frozenset({"POST_CLOSE", "AUDIT"})
STATES = frozenset({"STARTED", "PROGRESS", "COMPLETED", "FAILED"})


class ShadowLifecycleConfigError(ValueError):
    """The lifecycle configuration is malformed or widens authority."""


@dataclass(frozen=True, slots=True)
class ShadowLifecycleConfig:
    audit_config: str
    audit_config_file_sha256: str
    database: str
    collection_max_minutes: int
    progress_stale_minutes: int
    audit_max_minutes: int
    config_hash: str
    lifecycle_version: str = "12L.1.0"


def load_shadow_lifecycle_config(path: str | Path) -> ShadowLifecycleConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "lifecycle_version",
        "mode",
        "audit_config",
        "audit_config_file_sha256",
        "database",
        "collection_max_minutes",
        "progress_stale_minutes",
        "audit_max_minutes",
        "authority",
    }
    authority = {
        "database_read_enabled": True,
        "lifecycle_append_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "order_api_enabled": False,
        "session_retry_enabled": False,
        "backfill_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["lifecycle_version"] != "12L.1.0"
        or raw["mode"] != "APPEND_ONLY_SHADOW_OPERATION_LIFECYCLE"
        or raw["authority"] != authority
        or not _relative(raw.get("audit_config"))
        or not _relative(raw.get("database"))
        or not _sha(raw.get("audit_config_file_sha256"))
        or not _minutes(raw.get("collection_max_minutes"), 180)
        or not _minutes(raw.get("progress_stale_minutes"), 60)
        or not _minutes(raw.get("audit_max_minutes"), 60)
    ):
        raise ShadowLifecycleConfigError("Phase 12L lifecycle configuration is invalid")
    return ShadowLifecycleConfig(
        audit_config=str(raw["audit_config"]),
        audit_config_file_sha256=str(raw["audit_config_file_sha256"]),
        database=str(raw["database"]),
        collection_max_minutes=int(raw["collection_max_minutes"]),
        progress_stale_minutes=int(raw["progress_stale_minutes"]),
        audit_max_minutes=int(raw["audit_max_minutes"]),
        config_hash=canonical_hash(_freeze(raw)),
    )


def record_shadow_operation_event(
    config: ShadowLifecycleConfig,
    *,
    project_root: str | Path,
    session_id: str,
    operation: str,
    state: str,
    stage: str,
    observed_at: datetime,
    details: Mapping[str, object] | None = None,
    database_override: str | Path | None = None,
) -> Mapping[str, object]:
    """Append one immutable local lifecycle event without network authority."""
    _require_utc(observed_at)
    if operation not in OPERATIONS or state not in STATES or not stage.strip():
        raise ValueError("Phase 12L operation event is invalid")
    root = Path(project_root).resolve()
    schedule = _validated_schedule(root, config)
    if not any(item.session_id == session_id for item in schedule.sessions):
        raise ValueError("Phase 12L session is not in the frozen schedule")
    safe_details = {} if details is None else dict(details)
    payload = {
        "session_id": session_id,
        "plan_id": schedule.plan_id,
        "operation": operation,
        "state": state,
        "stage": stage,
        "observed_at": observed_at,
        "details": safe_details,
        "lifecycle_config_hash": config.config_hash,
        "network_used": False,
        "credentials_loaded": False,
        "broker_write_performed": False,
        "order_api_available": False,
        "session_retry_performed": False,
        "backfill_performed": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    event_id = deterministic_id(
        "paper_shadow_operation_event",
        (session_id, operation, state, stage, observed_at, config.config_hash),
    )
    full = {"event_id": event_id, **payload}
    payload_json, payload_hash = canonical_json(full), canonical_hash(full)
    database = _contained(
        root, config.database if database_override is None else database_override
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.connection.execute(
            """INSERT OR IGNORE INTO paper_shadow_operation_events
               (event_id,session_id,plan_id,operation,state,stage,observed_at,
                config_hash,details_json,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                session_id,
                schedule.plan_id,
                operation,
                state,
                stage,
                _time(observed_at),
                config.config_hash,
                canonical_json(safe_details),
                payload_json,
                payload_hash,
            ),
        )
        repository.connection.commit()
    return MappingProxyType(full)


def latest_shadow_operation_event(
    database: Path, session_id: str, operation: str
) -> Mapping[str, object] | None:
    """Read the latest lifecycle event from an already-resolved database path."""
    if operation not in OPERATIONS or not database.is_file():
        return None
    with SQLiteRepository(database) as repository:
        table = repository.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='paper_shadow_operation_events'"
        ).fetchone()
        if table is None:
            return None
        row = repository.connection.execute(
            """SELECT payload_json FROM paper_shadow_operation_events
               WHERE session_id=? AND operation=?
               ORDER BY observed_at DESC,event_id DESC LIMIT 1""",
            (session_id, operation),
        ).fetchone()
    if row is None:
        return None
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise ValueError("Phase 12L stored lifecycle payload is invalid")
    return MappingProxyType(payload)


def _validated_schedule(
    root: Path, config: ShadowLifecycleConfig
) -> ProspectiveShadowScheduleConfig:
    audit_path = _contained(root, config.audit_config)
    digest = "sha256:" + hashlib.sha256(audit_path.read_bytes()).hexdigest()
    if digest != config.audit_config_file_sha256:
        raise ValueError("Phase 12L audit configuration bytes drifted")
    audit = load_prospective_shadow_audit_config(audit_path)
    if audit.database != config.database:
        raise ValueError("Phase 12L lifecycle database does not match audit database")
    return load_prospective_shadow_schedule(_contained(root, audit.schedule))


def _contained(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("Phase 12L path escapes project root")
    return resolved


def _relative(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not Path(value).is_absolute()


def _sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _minutes(value: object, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= maximum


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12L timestamp must be UTC")


def _time(value: datetime) -> str:
    _require_utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
