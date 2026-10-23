"""Read-only Phase 12H watchdog for unattended SHADOW scheduling."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from trading_system.paper.prospective_shadow_audit import (
    load_prospective_shadow_audit_config,
)
from trading_system.paper.prospective_shadow_lifecycle import (
    latest_shadow_operation_event,
    load_shadow_lifecycle_config,
)
from trading_system.paper.prospective_shadow_orchestrator import (
    load_prospective_shadow_schedule,
)
from trading_system.serialization import canonical_hash


class ProspectiveShadowWatchdogConfigError(ValueError):
    """The Phase 12H watchdog configuration is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class ProspectiveShadowWatchdogConfig:
    audit_config: str
    audit_config_file_sha256: str
    database: str
    start_check_delay_minutes: int
    post_close_check_delay_minutes: int
    audit_check_delay_minutes: int
    config_hash: str
    lifecycle_config: str | None = None
    lifecycle_config_file_sha256: str | None = None
    watchdog_version: str = "12H.1.0"


def load_prospective_shadow_watchdog_config(
    path: str | Path,
) -> ProspectiveShadowWatchdogConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_12h = {
        "watchdog_version",
        "mode",
        "audit_config",
        "audit_config_file_sha256",
        "database",
        "start_check_delay_minutes",
        "post_close_check_delay_minutes",
        "audit_check_delay_minutes",
        "authority",
    }
    expected_12l = expected_12h | {
        "lifecycle_config",
        "lifecycle_config_file_sha256",
    }
    authority = {
        "database_read_enabled": True,
        "local_alert_write_enabled": True,
        "scheduler_write_enabled": False,
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
        or set(raw) not in (expected_12h, expected_12l)
        or raw["watchdog_version"] not in ("12H.1.0", "12L.1.0")
        or (raw["watchdog_version"] == "12H.1.0" and set(raw) != expected_12h)
        or (raw["watchdog_version"] == "12L.1.0" and set(raw) != expected_12l)
        or raw["mode"] != "LOCAL_READ_ONLY_SCHEDULE_WATCHDOG"
        or raw["authority"] != authority
        or not _relative(raw.get("audit_config"))
        or not _relative(raw.get("database"))
        or not _sha(raw.get("audit_config_file_sha256"))
        or not _minutes(raw.get("start_check_delay_minutes"), maximum=60)
        or not _minutes(raw.get("post_close_check_delay_minutes"), maximum=60)
        or not _minutes(raw.get("audit_check_delay_minutes"), maximum=60)
        or (
            raw["watchdog_version"] == "12L.1.0"
            and (
                not _relative(raw.get("lifecycle_config"))
                or not _sha(raw.get("lifecycle_config_file_sha256"))
            )
        )
    ):
        raise ProspectiveShadowWatchdogConfigError(
            "Phase 12H watchdog configuration is invalid or unsafe"
        )
    return ProspectiveShadowWatchdogConfig(
        str(raw["audit_config"]),
        str(raw["audit_config_file_sha256"]),
        str(raw["database"]),
        int(raw["start_check_delay_minutes"]),
        int(raw["post_close_check_delay_minutes"]),
        int(raw["audit_check_delay_minutes"]),
        canonical_hash(_freeze(raw)),
        None if raw["watchdog_version"] == "12H.1.0" else str(raw["lifecycle_config"]),
        None
        if raw["watchdog_version"] == "12H.1.0"
        else str(raw["lifecycle_config_file_sha256"]),
        str(raw["watchdog_version"]),
    )


def inspect_prospective_shadow_watchdog(
    config: ProspectiveShadowWatchdogConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> Mapping[str, object]:
    """Inspect immutable receipts using a SQLite read-only connection."""
    _require_utc(as_of)
    root = Path(project_root).resolve()
    audit_path = _contained(root, config.audit_config)
    audit_digest = "sha256:" + hashlib.sha256(audit_path.read_bytes()).hexdigest()
    if audit_digest != config.audit_config_file_sha256:
        raise ValueError("Phase 12H watchdog audit configuration bytes drifted")
    audit = load_prospective_shadow_audit_config(audit_path)
    schedule_path = _contained(root, audit.schedule)
    schedule_digest = "sha256:" + hashlib.sha256(schedule_path.read_bytes()).hexdigest()
    if schedule_digest != audit.schedule_file_sha256:
        raise ValueError("Phase 12H watchdog schedule bytes drifted")
    schedule = load_prospective_shadow_schedule(schedule_path)
    lifecycle = None
    if config.lifecycle_config is not None:
        lifecycle_path = _contained(root, config.lifecycle_config)
        lifecycle_digest = (
            "sha256:" + hashlib.sha256(lifecycle_path.read_bytes()).hexdigest()
        )
        if lifecycle_digest != config.lifecycle_config_file_sha256:
            raise ValueError("Phase 12L watchdog lifecycle configuration bytes drifted")
        lifecycle = load_shadow_lifecycle_config(lifecycle_path)
        if lifecycle.database != config.database:
            raise ValueError("Phase 12L watchdog lifecycle database drifted")
    market_day = as_of.astimezone(ZoneInfo("America/New_York")).date()
    session = next(
        (item for item in schedule.sessions if item.market_day == market_day), None
    )
    base = {
        "as_of": as_of,
        "market_day": market_day,
        "plan_id": schedule.plan_id,
        "watchdog_config_hash": config.config_hash,
        "network_used": False,
        "credentials_loaded": False,
        "database_write_performed": False,
        "scheduler_modified": False,
        "broker_write_performed": False,
        "order_api_available": False,
        "session_retry_performed": False,
        "backfill_performed": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if session is None:
        return MappingProxyType(
            {
                **base,
                "status": "NO_FROZEN_SESSION",
                "alert_required": False,
                "alert_code": None,
                "session_id": None,
                "expected_checkpoint": None,
                "next_checkpoint_at": None,
                "start_receipt_present": False,
                "post_close_receipt_present": False,
                "audit_status": None,
            }
        )

    start_due = session.open_at + timedelta(
        minutes=config.start_check_delay_minutes
    )
    post_close_due = session.collect_at + timedelta(
        minutes=config.post_close_check_delay_minutes
    )
    audit_at = session.collect_at + timedelta(
        minutes=schedule.completion_grace_minutes + audit.audit_delay_minutes
    )
    audit_due = audit_at + timedelta(minutes=config.audit_check_delay_minutes)
    database = _contained(
        root, config.database if database_override is None else database_override
    )
    start_present, post_close_present, audit_status = _evidence(
        database, session.session_id
    )
    post_event = latest_shadow_operation_event(database, session.session_id, "POST_CLOSE")
    audit_event = latest_shadow_operation_event(database, session.session_id, "AUDIT")

    status: str
    alert_code: str | None
    expected: str
    next_at: datetime | None
    if as_of < start_due:
        status = "PENDING_START_CHECK"
        alert_code = None
        expected = "START"
        next_at = start_due
    elif not start_present:
        status = "ALERT_MISSING_START"
        alert_code = "MISSING_START_RECEIPT"
        expected = "START"
        next_at = post_close_due
    elif as_of < post_close_due:
        status = "HEALTHY_START"
        alert_code = None
        expected = "POST_CLOSE"
        next_at = post_close_due
    elif not post_close_present:
        status, alert_code, next_at = _missing_operation_status(
            operation="POST_CLOSE",
            event=post_event,
            as_of=as_of,
            default_next=audit_due,
            maximum_minutes=None if lifecycle is None else lifecycle.collection_max_minutes,
            progress_stale_minutes=None
            if lifecycle is None
            else lifecycle.progress_stale_minutes,
        )
        expected = "POST_CLOSE"
    elif as_of < audit_due:
        status = "HEALTHY_POST_CLOSE"
        alert_code = None
        expected = "AUDIT"
        next_at = audit_due
    elif audit_status is None:
        status, alert_code, next_at = _missing_operation_status(
            operation="AUDIT",
            event=audit_event,
            as_of=as_of,
            default_next=None,
            maximum_minutes=None if lifecycle is None else lifecycle.audit_max_minutes,
            progress_stale_minutes=None
            if lifecycle is None
            else lifecycle.progress_stale_minutes,
        )
        expected = "AUDIT"
    elif audit_status != "COMPLETE":
        status = "ALERT_INCOMPLETE_AUDIT"
        alert_code = audit_status
        expected = "AUDIT"
        next_at = None
    else:
        status = "HEALTHY_COMPLETE"
        alert_code = None
        expected = "COMPLETE"
        next_at = None

    return MappingProxyType(
        {
            **base,
            "status": status,
            "alert_required": alert_code is not None,
            "alert_code": alert_code,
            "session_id": session.session_id,
            "expected_checkpoint": expected,
            "next_checkpoint_at": next_at,
            "start_receipt_present": start_present,
            "post_close_receipt_present": post_close_present,
            "audit_status": audit_status,
            "post_close_lifecycle_state": _event_value(post_event, "state"),
            "audit_lifecycle_state": _event_value(audit_event, "state"),
        }
    )


def _missing_operation_status(
    *,
    operation: str,
    event: Mapping[str, object] | None,
    as_of: datetime,
    default_next: datetime | None,
    maximum_minutes: int | None,
    progress_stale_minutes: int | None,
) -> tuple[str, str | None, datetime | None]:
    missing_status = f"ALERT_MISSING_{operation}"
    missing_code = "MISSING_DAILY_AUDIT" if operation == "AUDIT" else "MISSING_POST_CLOSE_RECEIPT"
    if event is None or maximum_minutes is None or progress_stale_minutes is None:
        return missing_status, missing_code, default_next
    state = str(event.get("state"))
    if state == "FAILED":
        return f"ALERT_{operation}_FAILED", f"{operation}_FAILED", None
    if state == "COMPLETED":
        return f"ALERT_{operation}_RECEIPT_MISSING", f"{operation}_RECEIPT_MISSING", None
    if state not in {"STARTED", "PROGRESS"}:
        return missing_status, missing_code, default_next
    observed = _event_time(event.get("observed_at"))
    allowed_minutes = (
        min(maximum_minutes, progress_stale_minutes)
        if state == "PROGRESS"
        else maximum_minutes
    )
    deadline = observed + timedelta(minutes=allowed_minutes)
    if as_of <= deadline:
        return f"HEALTHY_{operation}_RUNNING", None, deadline
    return f"ALERT_{operation}_TIMEOUT", f"{operation}_TIMEOUT", None


def _event_value(event: Mapping[str, object] | None, key: str) -> object:
    return None if event is None else event.get(key)


def _event_time(value: object) -> datetime:
    if isinstance(value, dict):
        value = value.get("__datetime__")
    if not isinstance(value, str):
        raise ValueError("Phase 12L lifecycle event timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_utc(parsed)
    return parsed


def _evidence(database: Path, session_id: str) -> tuple[bool, bool, str | None]:
    if not database.is_file():
        return False, False, None
    uri = f"file:{database.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        receipt_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='paper_shadow_orchestration_receipts'"
        ).fetchone()
        actions: set[str] = set()
        if receipt_table is not None:
            rows = connection.execute(
                "SELECT action FROM paper_shadow_orchestration_receipts "
                "WHERE session_id=?",
                (session_id,),
            ).fetchall()
            actions = {str(row[0]) for row in rows}
        audit_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='paper_shadow_daily_audits'"
        ).fetchone()
        audit_status: str | None = None
        if audit_table is not None:
            row = connection.execute(
                "SELECT status FROM paper_shadow_daily_audits WHERE session_id=?",
                (session_id,),
            ).fetchone()
            audit_status = None if row is None else str(row[0])
    return "START" in actions, "POST_CLOSE" in actions, audit_status


def _contained(root: Path, value: str | Path) -> Path:
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12H path escapes the project root")
    return candidate


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12H timestamp must be UTC")


def _relative(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not Path(value).is_absolute()


def _sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _minutes(value: object, *, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= maximum


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
