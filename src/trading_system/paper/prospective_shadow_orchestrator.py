"""Phase 12C deterministic unattended SHADOW-session orchestration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from trading_system.market_data import XNYSCalendar
from trading_system.paper.prospective_shadow_launch import (
    load_prospective_shadow_launch_config,
    start_prospective_shadow_session,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id
from trading_system.webull.burn_in_decision_worker import (
    load_burn_in_decision_worker_config,
)
from trading_system.webull.burn_in_worker import load_burn_in_worker_config


class ProspectiveShadowScheduleConfigError(ValueError):
    """The Phase 12C schedule or its authority boundary is malformed."""


@dataclass(frozen=True, slots=True)
class ScheduledShadowSession:
    market_day: date
    session_id: str
    open_at: datetime
    close_at: datetime
    collect_at: datetime


@dataclass(frozen=True, slots=True)
class ProspectiveShadowScheduleConfig:
    plan_path: str
    plan_id: str
    plan_file_sha256: str
    launch_config: str
    runtime_lock: str
    webull_config: str
    worker_config: str
    decision_config: str
    thresholds_config: str
    database: str
    calendar_version: str
    start_grace_minutes: int
    completion_grace_minutes: int
    sessions: tuple[ScheduledShadowSession, ...]
    config_hash: str
    orchestrator_version: str = "12C.1.0"


def load_prospective_shadow_schedule(
    path: str | Path,
) -> ProspectiveShadowScheduleConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "orchestrator_version",
        "mode",
        "plan",
        "plan_id",
        "plan_file_sha256",
        "launch_config",
        "runtime_lock",
        "webull_config",
        "worker_config",
        "decision_config",
        "thresholds_config",
        "database",
        "calendar",
        "calendar_version",
        "start_grace_minutes",
        "completion_grace_minutes",
        "sessions",
        "authority",
    }
    authority = {
        "local_process_launch_enabled": True,
        "database_read_enabled": True,
        "database_write_enabled": True,
        "network_read_enabled": True,
        "credential_loading_enabled": True,
        "broker_writes_enabled": False,
        "order_api_enabled": False,
        "sandbox_execution_enabled": False,
        "simulated_fills_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    paths = (
        "plan",
        "launch_config",
        "runtime_lock",
        "webull_config",
        "worker_config",
        "decision_config",
        "thresholds_config",
        "database",
    )
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["orchestrator_version"] != "12C.1.0"
        or raw["mode"] != "AUTOMATIC_LOCAL_SHADOW_ONLY"
        or raw["calendar"] != "XNYS"
        or raw["calendar_version"] != "exchange-calendars-4"
        or raw["authority"] != authority
        or any(not _relative(raw.get(name)) for name in paths)
        or not _sha(raw.get("plan_file_sha256"))
        or not isinstance(raw.get("plan_id"), str)
        or not raw["plan_id"]
        or not _bounded_minutes(raw.get("start_grace_minutes"), maximum=30)
        or not _bounded_minutes(raw.get("completion_grace_minutes"), maximum=240)
    ):
        raise ProspectiveShadowScheduleConfigError(
            "Phase 12C schedule configuration is invalid or unsafe"
        )
    sessions_raw = raw["sessions"]
    if not isinstance(sessions_raw, list) or len(sessions_raw) != 20:
        raise ProspectiveShadowScheduleConfigError(
            "Phase 12C schedule must contain exactly twenty XNYS sessions"
        )
    sessions = tuple(_session(item) for item in sessions_raw)
    if sessions != tuple(sorted(sessions, key=lambda item: item.market_day)):
        raise ProspectiveShadowScheduleConfigError("Phase 12C sessions are not ordered")
    if len({item.market_day for item in sessions}) != len(sessions) or len(
        {item.session_id for item in sessions}
    ) != len(sessions):
        raise ProspectiveShadowScheduleConfigError("Phase 12C sessions are not unique")
    calendar = XNYSCalendar()
    for item in sessions:
        bounds = calendar.bounds(item.market_day)
        if (
            bounds != (item.open_at, item.close_at)
            or item.collect_at != item.close_at + timedelta(minutes=5)
            or item.session_id != f"burn-in-shadow-{item.market_day:%Y%m%d}-01"
        ):
            raise ProspectiveShadowScheduleConfigError(
                "Phase 12C session does not match the frozen XNYS calendar"
            )
    return ProspectiveShadowScheduleConfig(
        str(raw["plan"]),
        str(raw["plan_id"]),
        str(raw["plan_file_sha256"]),
        str(raw["launch_config"]),
        str(raw["runtime_lock"]),
        str(raw["webull_config"]),
        str(raw["worker_config"]),
        str(raw["decision_config"]),
        str(raw["thresholds_config"]),
        str(raw["database"]),
        str(raw["calendar_version"]),
        int(raw["start_grace_minutes"]),
        int(raw["completion_grace_minutes"]),
        sessions,
        canonical_hash(_freeze(raw)),
    )


def inspect_scheduled_shadow_preflight(
    config: ProspectiveShadowScheduleConfig,
    *,
    schedule_path: str | Path,
    project_root: str | Path,
    as_of: datetime,
) -> Mapping[str, object]:
    """Validate frozen inputs shortly before a scheduled start without side effects."""
    _require_utc(as_of)
    root = Path(project_root).resolve()
    _validate_frozen_inputs(root, config)
    resolved_schedule = _contained(root, schedule_path)
    market_day = as_of.astimezone(ZoneInfo("America/New_York")).date()
    scheduled = next(
        (item for item in config.sessions if item.market_day == market_day), None
    )
    eligible = bool(
        scheduled is not None
        and scheduled.open_at - timedelta(minutes=30) <= as_of <= scheduled.open_at
    )
    if scheduled is None:
        reason = "NOT_A_FROZEN_XNYS_SESSION"
    elif eligible:
        reason = "PREFLIGHT_READY"
    else:
        reason = "OUTSIDE_PREFLIGHT_WINDOW"
    return MappingProxyType(
        {
            "eligible": eligible,
            "reason": reason,
            "plan_id": config.plan_id,
            "session_id": None if scheduled is None else scheduled.session_id,
            "market_day": None if scheduled is None else scheduled.market_day,
            "open_at": None if scheduled is None else scheduled.open_at,
            "checked_at": as_of,
            "schedule_path_hash": "sha256:"
            + hashlib.sha256(resolved_schedule.read_bytes()).hexdigest(),
            "frozen_identity_valid": True,
            "network_used": False,
            "credentials_loaded": False,
            "broker_write_performed": False,
            "order_api_available": False,
            "session_started": False,
        }
    )


def inspect_scheduled_shadow_target(
    config: ProspectiveShadowScheduleConfig,
    *,
    as_of: datetime,
    action: str,
) -> Mapping[str, object]:
    """Resolve the current frozen session without touching the database or network."""
    _require_utc(as_of)
    normalized_action = action.upper()
    if normalized_action not in {"START", "POST_CLOSE"}:
        raise ValueError("Phase 12C action must be START or POST_CLOSE")
    market_day = as_of.astimezone(ZoneInfo("America/New_York")).date()
    scheduled = next(
        (item for item in config.sessions if item.market_day == market_day), None
    )
    if scheduled is None:
        return MappingProxyType(
            {
                "eligible": False,
                "reason": "NOT_A_FROZEN_XNYS_SESSION",
                "action": normalized_action,
                "market_day": market_day,
                "network_used": False,
                "broker_write_performed": False,
            }
        )
    if normalized_action == "START":
        earliest = scheduled.open_at
        latest = scheduled.open_at + timedelta(minutes=config.start_grace_minutes)
    else:
        earliest = scheduled.collect_at
        latest = scheduled.collect_at + timedelta(
            minutes=config.completion_grace_minutes
        )
    eligible = earliest <= as_of <= latest
    return MappingProxyType(
        {
            "eligible": eligible,
            "reason": "ELIGIBLE" if eligible else "OUTSIDE_ACTION_WINDOW",
            "action": normalized_action,
            "market_day": market_day,
            "session_id": scheduled.session_id,
            "open_at": scheduled.open_at,
            "close_at": scheduled.close_at,
            "collect_at": scheduled.collect_at,
            "window_earliest": earliest,
            "window_latest": latest,
            "network_used": False,
            "broker_write_performed": False,
        }
    )


def start_scheduled_shadow_day(
    config: ProspectiveShadowScheduleConfig,
    *,
    schedule_path: str | Path,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> Mapping[str, object]:
    """Start today's idempotent SHADOW session and append a local start receipt."""
    root = Path(project_root).resolve()
    _validate_frozen_inputs(root, config)
    target = inspect_scheduled_shadow_target(config, as_of=as_of, action="START")
    if not target["eligible"]:
        raise ValueError(f"Phase 12C start is not eligible: {target['reason']}")
    database = _database_path(root, config, database_override)
    session_id = str(target["session_id"])
    with SQLiteRepository(database) as repository:
        repository.migrate()
        existing = _receipt(repository, session_id, "START")
    if existing is not None:
        return existing
    started_at = _existing_binding_start(database, session_id) or as_of
    launch = start_prospective_shadow_session(
        database=database,
        config_path=config.launch_config,
        runtime_lock_path=config.runtime_lock,
        project_root=root,
        session_id=session_id,
        started_at=started_at,
    )
    payload = {
        "action": "START",
        "status": "SHADOW_SESSION_STARTED",
        "session_id": session_id,
        "plan_id": config.plan_id,
        "market_day": target["market_day"],
        "scheduled_at": target["open_at"],
        "observed_at": started_at,
        "binding_id": launch["binding_id"],
        "schedule_config_hash": config.config_hash,
        "schedule_path_hash": canonical_hash(str(schedule_path)),
        "network_read_used": False,
        "credentials_loaded": False,
        "broker_write_performed": False,
        "order_api_available": False,
        "simulated_fills_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    with SQLiteRepository(database) as repository:
        repository.migrate()
        return _insert_receipt(repository, payload)


def complete_scheduled_shadow_day(
    config: ProspectiveShadowScheduleConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    database_override: str | Path | None = None,
) -> Mapping[str, object]:
    """Seal a day only after same-session read-only data and decision cycles exist."""
    root = Path(project_root).resolve()
    _validate_frozen_inputs(root, config)
    target = inspect_scheduled_shadow_target(config, as_of=as_of, action="POST_CLOSE")
    if not target["eligible"]:
        raise ValueError(f"Phase 12C completion is not eligible: {target['reason']}")
    database = _database_path(root, config, database_override)
    session_id = str(target["session_id"])
    with SQLiteRepository(database) as repository:
        repository.migrate()
        existing = _receipt(repository, session_id, "POST_CLOSE")
        if existing is not None:
            return existing
        start_receipt = _receipt(repository, session_id, "START")
        if start_receipt is None:
            raise ValueError("Phase 12C completion requires the immutable start receipt")
        verification = repository.connection.execute(
            """SELECT verification_id,occurred_at FROM webull_connection_verifications
               WHERE session_id=? AND occurred_at<=? ORDER BY occurred_at DESC LIMIT 1""",
            (session_id, _time(as_of)),
        ).fetchone()
        worker = repository.connection.execute(
            """SELECT cycle_id,observed_at,network_used,payload_json
               FROM webull_burn_in_worker_cycles
               WHERE session_id=? AND observed_at<=? ORDER BY observed_at DESC LIMIT 1""",
            (session_id, _time(as_of)),
        ).fetchone()
        if verification is None or worker is None or int(worker[2]) != 1:
            raise ValueError(
                "Phase 12C completion requires same-session verification and network-read data"
            )
        worker_payload = _payload(worker[3], "worker")
        if worker_payload.get("broker_write_performed") is not False:
            raise ValueError("Phase 12C worker receipt does not prove zero broker writes")
        decision = repository.connection.execute(
            """SELECT cycle_id,observed_at,payload_json FROM burn_in_shadow_decision_cycles
               WHERE session_id=? AND observed_at>=? AND observed_at<=?
               ORDER BY observed_at DESC LIMIT 1""",
            (session_id, str(worker[1]), _time(as_of)),
        ).fetchone()
        if decision is None:
            raise ValueError("Phase 12C completion requires the causal decision cycle")
        decision_payload = _payload(decision[2], "decision")
        if decision_payload.get("broker_write_performed") is not False:
            raise ValueError("Phase 12C decision receipt does not prove zero broker writes")
        payload = {
            "action": "POST_CLOSE",
            "status": "POST_CLOSE_CYCLES_COMPLETED",
            "session_id": session_id,
            "plan_id": config.plan_id,
            "market_day": target["market_day"],
            "scheduled_at": target["collect_at"],
            "observed_at": as_of,
            "verification_id": str(verification[0]),
            "worker_cycle_id": str(worker[0]),
            "decision_cycle_id": str(decision[0]),
            "schedule_config_hash": config.config_hash,
            "network_read_used": True,
            "credentials_loaded": True,
            "broker_write_performed": False,
            "order_api_available": False,
            "simulated_fills_enabled": False,
            "live_trading_enabled": False,
            "automatic_promotion_enabled": False,
            "regime_annotation_recorded": False,
        }
        return _insert_receipt(repository, payload)


def _validate_frozen_inputs(root: Path, config: ProspectiveShadowScheduleConfig) -> None:
    plan_path = _contained(root, config.plan_path)
    plan_hash = "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    launch = load_prospective_shadow_launch_config(_contained(root, config.launch_config))
    worker = load_burn_in_worker_config(_contained(root, config.worker_config))
    decision = load_burn_in_decision_worker_config(_contained(root, config.decision_config))
    if (
        plan_hash != config.plan_file_sha256
        or plan.get("plan_id") != config.plan_id
        or launch.plan_id != config.plan_id
        or worker.plan_id != config.plan_id
        or decision.plan_id != config.plan_id
        or launch.worker_config != config.worker_config
        or launch.decision_config != config.decision_config
        or launch.calendar_version != config.calendar_version
        or launch.window_start > config.sessions[0].open_at
        or launch.window_end < config.sessions[-1].collect_at
    ):
        raise ValueError("Phase 12C frozen plan and runtime identities do not match")


def _insert_receipt(
    repository: SQLiteRepository, payload: Mapping[str, object]
) -> Mapping[str, object]:
    action = str(payload["action"])
    session_id = str(payload["session_id"])
    receipt_id = deterministic_id(
        "paper_shadow_orchestration_receipt",
        (session_id, action, payload["scheduled_at"], payload["schedule_config_hash"]),
    )
    full = {"receipt_id": receipt_id, **payload}
    payload_json = canonical_json(full)
    payload_hash = canonical_hash(full)
    cursor = repository.connection.execute(
        """INSERT OR IGNORE INTO paper_shadow_orchestration_receipts
           (receipt_id,session_id,plan_id,market_day,action,scheduled_at,observed_at,
            worker_cycle_id,decision_cycle_id,status,config_hash,network_read_used,
            broker_write_performed,payload_json,payload_hash)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            receipt_id,
            session_id,
            payload["plan_id"],
            str(payload["market_day"]),
            action,
            _time(payload["scheduled_at"]),
            _time(payload["observed_at"]),
            payload.get("worker_cycle_id"),
            payload.get("decision_cycle_id"),
            payload["status"],
            payload["schedule_config_hash"],
            int(bool(payload["network_read_used"])),
            int(bool(payload["broker_write_performed"])),
            payload_json,
            payload_hash,
        ),
    )
    if cursor.rowcount == 0:
        existing = _receipt(repository, session_id, action)
        if existing is None or existing.get("receipt_id") != receipt_id:
            raise ValueError("conflicting Phase 12C orchestration receipt")
        return existing
    repository.connection.commit()
    return MappingProxyType(full)


def _receipt(
    repository: SQLiteRepository, session_id: str, action: str
) -> Mapping[str, object] | None:
    row = repository.connection.execute(
        """SELECT payload_json FROM paper_shadow_orchestration_receipts
           WHERE session_id=? AND action=?""",
        (session_id, action),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(str(row[0]))
    if not isinstance(payload, dict):
        raise ValueError("Phase 12C stored receipt is invalid")
    return MappingProxyType(payload)


def _existing_binding_start(database: Path, session_id: str) -> datetime | None:
    if not database.exists():
        return None
    with SQLiteRepository(database) as repository:
        repository.migrate()
        row = repository.connection.execute(
            "SELECT started_at FROM paper_burn_in_session_bindings WHERE session_id=?",
            (session_id,),
        ).fetchone()
    return None if row is None else _parse_time(row[0])


def _database_path(
    root: Path,
    config: ProspectiveShadowScheduleConfig,
    override: str | Path | None,
) -> Path:
    value = config.database if override is None else override
    return _contained(root, value)


def _session(value: object) -> ScheduledShadowSession:
    if not isinstance(value, dict) or set(value) != {
        "market_day",
        "session_id",
        "open_at",
        "close_at",
        "collect_at",
    }:
        raise ProspectiveShadowScheduleConfigError("Phase 12C session keys are invalid")
    try:
        return ScheduledShadowSession(
            date.fromisoformat(str(value["market_day"])),
            str(value["session_id"]),
            _parse_time(value["open_at"]),
            _parse_time(value["close_at"]),
            _parse_time(value["collect_at"]),
        )
    except (TypeError, ValueError) as exc:
        raise ProspectiveShadowScheduleConfigError(
            "Phase 12C session values are invalid"
        ) from exc


def _payload(value: object, label: str) -> dict[str, object]:
    loaded = json.loads(str(value))
    if not isinstance(loaded, dict):
        raise ValueError(f"Phase 12C {label} payload is invalid")
    return {str(key): item for key, item in loaded.items()}


def _bounded_minutes(value: object, *, maximum: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and 1 <= value <= maximum
    )


def _contained(root: Path, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError("Phase 12C path must be text")
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12C path escapes project root")
    return candidate


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Phase 12C timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require_utc(parsed)
    return parsed


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12C timestamps must be UTC")


def _time(value: object) -> str:
    if not isinstance(value, datetime):
        raise ValueError("Phase 12C timestamp value is invalid")
    _require_utc(value)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value) == 71


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
