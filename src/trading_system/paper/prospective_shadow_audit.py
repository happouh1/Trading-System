"""Phase 12D immutable daily health audits for unattended SHADOW sessions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from trading_system.paper.prospective_shadow_orchestrator import (
    ProspectiveShadowScheduleConfig,
    ScheduledShadowSession,
    load_prospective_shadow_schedule,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class ProspectiveShadowAuditConfigError(ValueError):
    """The Phase 12D audit configuration is malformed or widens authority."""


@dataclass(frozen=True, slots=True)
class ProspectiveShadowAuditConfig:
    schedule: str
    schedule_file_sha256: str
    database: str
    audit_delay_minutes: int
    audit_grace_minutes: int
    config_hash: str
    audit_version: str = "12D.1.0"


def load_prospective_shadow_audit_config(
    path: str | Path,
) -> ProspectiveShadowAuditConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "audit_version",
        "mode",
        "schedule",
        "schedule_file_sha256",
        "database",
        "audit_delay_minutes",
        "audit_grace_minutes",
        "authority",
    }
    authority = {
        "database_read_enabled": True,
        "database_write_enabled": True,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "order_api_enabled": False,
        "session_retry_enabled": False,
        "backfill_enabled": False,
        "regime_classification_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["audit_version"] != "12D.1.0"
        or raw["mode"] != "FINAL_DAILY_SHADOW_HEALTH_AUDIT"
        or raw["authority"] != authority
        or not _relative(raw.get("schedule"))
        or not _relative(raw.get("database"))
        or not _sha(raw.get("schedule_file_sha256"))
        or not _bounded_minutes(raw.get("audit_delay_minutes"), maximum=30)
        or not _bounded_minutes(raw.get("audit_grace_minutes"), maximum=240)
    ):
        raise ProspectiveShadowAuditConfigError(
            "Phase 12D audit configuration is invalid or unsafe"
        )
    return ProspectiveShadowAuditConfig(
        str(raw["schedule"]),
        str(raw["schedule_file_sha256"]),
        str(raw["database"]),
        int(raw["audit_delay_minutes"]),
        int(raw["audit_grace_minutes"]),
        canonical_hash(_freeze(raw)),
    )


def inspect_shadow_audit_target(
    schedule: ProspectiveShadowScheduleConfig,
    audit: ProspectiveShadowAuditConfig,
    *,
    as_of: datetime,
) -> Mapping[str, object]:
    """Resolve today's final audit window without database or network access."""
    _require_utc(as_of)
    market_day = as_of.astimezone(ZoneInfo("America/New_York")).date()
    scheduled = next(
        (item for item in schedule.sessions if item.market_day == market_day), None
    )
    if scheduled is None:
        return MappingProxyType(
            {
                "eligible": False,
                "reason": "NOT_A_FROZEN_XNYS_SESSION",
                "market_day": market_day,
                "network_used": False,
                "broker_write_performed": False,
            }
        )
    earliest, latest = _audit_window(schedule, audit, scheduled)
    eligible = earliest <= as_of <= latest
    return MappingProxyType(
        {
            "eligible": eligible,
            "reason": "ELIGIBLE" if eligible else "OUTSIDE_AUDIT_WINDOW",
            "market_day": market_day,
            "session_id": scheduled.session_id,
            "audit_at": earliest,
            "window_earliest": earliest,
            "window_latest": latest,
            "network_used": False,
            "broker_write_performed": False,
        }
    )


def audit_scheduled_shadow_day(
    schedule: ProspectiveShadowScheduleConfig,
    audit: ProspectiveShadowAuditConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> Mapping[str, object]:
    """Append one final, idempotent audit without retrying or backfilling work."""
    root = Path(project_root).resolve()
    _validate_inputs(root, schedule, audit)
    target = inspect_shadow_audit_target(schedule, audit, as_of=as_of)
    if not target["eligible"]:
        raise ValueError(f"Phase 12D audit is not eligible: {target['reason']}")
    database = _contained(
        root, audit.database if database_override is None else database_override
    )
    session_id = str(target["session_id"])
    with SQLiteRepository(database) as repository:
        repository.migrate()
        existing = _stored_audit(repository, session_id)
        if existing is not None:
            return existing
        rows = repository.connection.execute(
            """SELECT action,plan_id,config_hash,broker_write_performed,payload_json
               FROM paper_shadow_orchestration_receipts WHERE session_id=?""",
            (session_id,),
        ).fetchall()
        receipts = {str(row[0]): row for row in rows}
        missing: list[str] = []
        if "START" not in receipts:
            missing.append("START_RECEIPT")
        if "POST_CLOSE" not in receipts:
            missing.append("POST_CLOSE_RECEIPT")
        unsafe = any(
            str(row[1]) != schedule.plan_id
            or str(row[2]) != schedule.config_hash
            or int(row[3]) != 0
            or _payload(row[4]).get("broker_write_performed") is not False
            for row in rows
        )
        if unsafe:
            status = "UNSAFE_EVIDENCE"
        elif not missing:
            status = "COMPLETE"
        elif "START_RECEIPT" in missing:
            status = "INCOMPLETE_START"
        else:
            status = "INCOMPLETE_POST_CLOSE"
        payload = {
            "status": status,
            "session_id": session_id,
            "plan_id": schedule.plan_id,
            "market_day": target["market_day"],
            "scheduled_at": target["audit_at"],
            "observed_at": as_of,
            "start_receipt_id": _receipt_id(receipts.get("START")),
            "post_close_receipt_id": _receipt_id(receipts.get("POST_CLOSE")),
            "missing_components": tuple(missing),
            "schedule_config_hash": schedule.config_hash,
            "audit_config_hash": audit.config_hash,
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_detected": unsafe,
            "broker_write_performed": False,
            "order_api_available": False,
            "session_retry_performed": False,
            "backfill_performed": False,
            "regime_annotation_recorded": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
        }
        return _insert_audit(repository, payload)


def shadow_audit_status(
    schedule: ProspectiveShadowScheduleConfig,
    audit: ProspectiveShadowAuditConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> Mapping[str, object]:
    """Return an offline aggregate without appending or mutating evidence."""
    _require_utc(as_of)
    root = Path(project_root).resolve()
    _validate_inputs(root, schedule, audit)
    database = _contained(
        root, audit.database if database_override is None else database_override
    )
    stored: dict[str, str] = {}
    if database.exists():
        with SQLiteRepository(database) as repository:
            table = repository.connection.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type='table' AND name='paper_shadow_daily_audits'"""
            ).fetchone()
            if table is not None:
                rows = repository.connection.execute(
                    """SELECT session_id,status FROM paper_shadow_daily_audits
                       WHERE plan_id=?""",
                    (schedule.plan_id,),
                ).fetchall()
                stored = {str(row[0]): str(row[1]) for row in rows}
    sessions: list[dict[str, object]] = []
    for item in schedule.sessions:
        due_at, _ = _audit_window(schedule, audit, item)
        status = stored.get(item.session_id)
        if status is None:
            status = "MISSING_AUDIT" if as_of > due_at else "PENDING"
        sessions.append(
            {
                "market_day": item.market_day,
                "session_id": item.session_id,
                "audit_due_at": due_at,
                "status": status,
            }
        )
    counts = {
        name: sum(1 for item in sessions if item["status"] == name)
        for name in (
            "COMPLETE",
            "INCOMPLETE_START",
            "INCOMPLETE_POST_CLOSE",
            "UNSAFE_EVIDENCE",
            "MISSING_AUDIT",
            "PENDING",
        )
    }
    return MappingProxyType(
        {
            "plan_id": schedule.plan_id,
            "as_of": as_of,
            "scheduled_sessions": len(schedule.sessions),
            "counts": counts,
            "sessions": tuple(sessions),
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_performed": False,
            "release_authorized": False,
        }
    )


def _audit_window(
    schedule: ProspectiveShadowScheduleConfig,
    audit: ProspectiveShadowAuditConfig,
    session: ScheduledShadowSession,
) -> tuple[datetime, datetime]:
    earliest = session.collect_at + timedelta(
        minutes=schedule.completion_grace_minutes + audit.audit_delay_minutes
    )
    return earliest, earliest + timedelta(minutes=audit.audit_grace_minutes)


def _validate_inputs(
    root: Path,
    schedule: ProspectiveShadowScheduleConfig,
    audit: ProspectiveShadowAuditConfig,
) -> None:
    schedule_path = _contained(root, audit.schedule)
    digest = "sha256:" + hashlib.sha256(schedule_path.read_bytes()).hexdigest()
    loaded = load_prospective_shadow_schedule(schedule_path)
    if digest != audit.schedule_file_sha256 or loaded != schedule:
        raise ValueError("Phase 12D audit is not bound to the frozen Phase 12C schedule")
    if audit.database != schedule.database:
        raise ValueError("Phase 12D audit database does not match the Phase 12C schedule")


def _insert_audit(
    repository: SQLiteRepository, payload: Mapping[str, object]
) -> Mapping[str, object]:
    session_id = str(payload["session_id"])
    audit_id = deterministic_id(
        "paper_shadow_daily_audit",
        (session_id, payload["scheduled_at"], payload["audit_config_hash"]),
    )
    full = {"audit_id": audit_id, **payload}
    payload_json, payload_hash = canonical_json(full), canonical_hash(full)
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO paper_shadow_daily_audits
           (audit_id,session_id,plan_id,market_day,scheduled_at,observed_at,status,
            missing_components_json,config_hash,broker_write_detected,payload_json,payload_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            audit_id,
            session_id,
            payload["plan_id"],
            str(payload["market_day"]),
            _time(payload["scheduled_at"]),
            _time(payload["observed_at"]),
            payload["status"],
            canonical_json(payload["missing_components"]),
            payload["audit_config_hash"],
            int(bool(payload["broker_write_detected"])),
            payload_json,
            payload_hash,
        ),
    )
    if cursor.rowcount == 0:
        existing = _stored_audit(repository, session_id)
        if existing is None or existing.get("audit_id") != audit_id:
            raise ValueError("conflicting Phase 12D daily audit")
        return existing
    repository.connection.commit()
    stored = _stored_audit(repository, session_id)
    if stored is None:
        raise ValueError("Phase 12D daily audit was not persisted")
    return stored


def _stored_audit(
    repository: SQLiteRepository, session_id: str
) -> Mapping[str, object] | None:
    row = repository.connection.execute(
        "SELECT payload_json FROM paper_shadow_daily_audits WHERE session_id=?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise ValueError("Phase 12D stored audit payload is invalid")
    return MappingProxyType(payload)


def _payload(value: object) -> dict[str, object]:
    loaded = json.loads(str(value))
    if not isinstance(loaded, dict):
        raise ValueError("Phase 12D orchestration payload is invalid")
    return {str(key): item for key, item in loaded.items()}


def _receipt_id(row: tuple[object, ...] | None) -> object:
    if row is None:
        return None
    payload = _payload(row[4])
    return payload.get("receipt_id")


def _contained(root: Path, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError("Phase 12D path must be text")
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12D path escapes project root")
    return candidate


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _bounded_minutes(value: object, *, maximum: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and 1 <= value <= maximum
    )


def _sha(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12D timestamps must be UTC")


def _time(value: object) -> str:
    if not isinstance(value, datetime):
        raise ValueError("Phase 12D timestamp value is invalid")
    _require_utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
