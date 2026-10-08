"""Offline Phase 12F operations dashboard for the frozen SHADOW cohort."""

from __future__ import annotations

import hashlib
import html
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import cast
from zoneinfo import ZoneInfo

from trading_system.paper.prospective_shadow_audit import (
    load_prospective_shadow_audit_config,
)
from trading_system.paper.prospective_shadow_orchestrator import (
    ProspectiveShadowScheduleConfig,
    ScheduledShadowSession,
    load_prospective_shadow_schedule,
)
from trading_system.serialization import canonical_hash, deterministic_id
from trading_system.webull.burn_in_worker import load_burn_in_worker_config


class ProspectiveShadowDashboardConfigError(ValueError):
    """The Phase 12F dashboard configuration is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class ProspectiveShadowDashboardConfig:
    audit_config: str
    task_snapshot: str
    log_root: str
    output: str
    expected_tasks: tuple[str, ...]
    config_hash: str
    dashboard_version: str = "12F.1.0"


@dataclass(frozen=True, slots=True)
class ProspectiveShadowDashboardArtifact:
    artifact_id: str
    snapshot_id: str
    output_path: str
    content_hash: str
    overall_status: str
    plan_id: str
    completed_sessions: int
    scheduled_sessions: int
    dashboard_version: str = "12F.1.0"
    mode: str = "READ_ONLY_BURN_IN_OPERATIONS"
    database_write_performed: bool = False
    scheduler_modified: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    order_api_available: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.artifact_id
            or not self.snapshot_id
            or not self.output_path
            or not self.content_hash.startswith("sha256:")
            or self.overall_status not in {"GREEN", "AMBER", "RED"}
            or not self.plan_id
            or not 0 <= self.completed_sessions <= self.scheduled_sessions
            or self.dashboard_version != "12F.1.0"
            or self.mode != "READ_ONLY_BURN_IN_OPERATIONS"
            or any(
                (
                    self.database_write_performed,
                    self.scheduler_modified,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.order_api_available,
                    self.live_trading_enabled,
                    self.automatic_promotion_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 12F dashboard artifact")


def load_prospective_shadow_dashboard_config(
    path: str | Path,
) -> ProspectiveShadowDashboardConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "dashboard_version",
        "mode",
        "audit_config",
        "task_snapshot",
        "log_root",
        "output",
        "expected_tasks",
        "authority",
    }
    authority = {
        "database_read_enabled": True,
        "artifact_write_enabled": True,
        "scheduler_read_enabled": True,
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
    tasks = raw.get("expected_tasks") if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["dashboard_version"] != "12F.1.0"
        or raw["mode"] != "READ_ONLY_BURN_IN_OPERATIONS"
        or raw["authority"] != authority
        or any(
            not _relative(raw.get(name))
            for name in ("audit_config", "task_snapshot", "log_root", "output")
        )
        or not str(raw["output"]).endswith(".html")
        or not isinstance(tasks, list)
        or len(tasks) != 4
        or any(not isinstance(item, str) or not item for item in tasks)
        or len(set(tasks)) != len(tasks)
    ):
        raise ProspectiveShadowDashboardConfigError(
            "Phase 12F dashboard configuration is invalid or unsafe"
        )
    return ProspectiveShadowDashboardConfig(
        str(raw["audit_config"]),
        str(raw["task_snapshot"]),
        str(raw["log_root"]),
        str(raw["output"]),
        tuple(tasks),
        canonical_hash(_freeze(raw)),
    )


def render_prospective_shadow_dashboard(
    config: ProspectiveShadowDashboardConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
    task_snapshot_override: str | Path | None = None,
) -> tuple[ProspectiveShadowDashboardArtifact, Mapping[str, object]]:
    """Render a static dashboard without changing source evidence or task state."""
    _require_utc(as_of)
    root = Path(project_root).resolve()
    audit_path = _contained(root, config.audit_config)
    audit = load_prospective_shadow_audit_config(audit_path)
    schedule_path = _contained(root, audit.schedule)
    schedule_digest = "sha256:" + hashlib.sha256(schedule_path.read_bytes()).hexdigest()
    if schedule_digest != audit.schedule_file_sha256:
        raise ValueError("Phase 12F audit is not bound to the frozen schedule bytes")
    schedule = load_prospective_shadow_schedule(schedule_path)
    worker = load_burn_in_worker_config(_contained(root, schedule.worker_config))
    if worker.plan_id != schedule.plan_id:
        raise ValueError("Phase 12F worker and schedule plan identities differ")
    task_path = _contained(
        root,
        config.task_snapshot if task_snapshot_override is None else task_snapshot_override,
    )
    tasks = _load_task_snapshot(task_path, config.expected_tasks)
    evidence = _read_evidence(
        _contained(root, audit.database),
        schedule,
        as_of=as_of,
        audit_delay_minutes=audit.audit_delay_minutes,
    )
    preflight = _preflight_status(root, config.log_root, schedule, as_of)
    snapshot = _snapshot(
        config,
        schedule,
        worker.symbols,
        tasks,
        evidence,
        preflight,
        as_of,
    )
    content = _dashboard_html(snapshot)
    output = _contained(root, config.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(output)
    artifact = ProspectiveShadowDashboardArtifact(
        deterministic_id(
            "prospective_shadow_dashboard_artifact",
            (snapshot["snapshot_id"], config.config_hash, canonical_hash(content)),
        ),
        str(snapshot["snapshot_id"]),
        str(output),
        canonical_hash(content),
        str(snapshot["overall_status"]),
        schedule.plan_id,
        _int_value(snapshot["completed_sessions"]),
        len(schedule.sessions),
    )
    return artifact, snapshot


def _snapshot(
    config: ProspectiveShadowDashboardConfig,
    schedule: ProspectiveShadowScheduleConfig,
    symbols: tuple[str, ...],
    tasks: tuple[Mapping[str, object], ...],
    evidence: Mapping[str, object],
    preflight: str,
    as_of: datetime,
) -> Mapping[str, object]:
    raw_sessions = evidence["sessions"]
    if not isinstance(raw_sessions, tuple):
        raise TypeError("validated Phase 12F sessions are invalid")
    sessions = cast(tuple[Mapping[str, object], ...], raw_sessions)
    today = as_of.astimezone(ZoneInfo("America/New_York")).date()
    current = next((item for item in sessions if item["market_day"] == today), None)
    next_session = next(
        (item for item in sessions if _date_value(item["market_day"]) >= today),
        None,
    )
    complete = sum(item["audit_status"] == "COMPLETE" for item in sessions)
    unsafe = bool(evidence["unsafe_evidence"])
    task_failure = any(_task_unhealthy(item) for item in tasks)
    operational_gap = any(
        item["audit_status"]
        in {"INCOMPLETE_START", "INCOMPLETE_POST_CLOSE", "MISSING_AUDIT"}
        for item in sessions
    )
    if unsafe or task_failure:
        overall = "RED"
    elif operational_gap:
        overall = "AMBER"
    else:
        overall = "GREEN"
    remaining = tuple(
        item["market_day"] for item in sessions if item["audit_status"] != "COMPLETE"
    )
    symbol_status = {
        symbol: (
            "COLLECTED"
            if current is not None and _int_value(current["worker_cycles"]) > 0
            else "PENDING"
        )
        for symbol in symbols
    }
    identity = {
        "plan_id": schedule.plan_id,
        "as_of": as_of,
        "tasks": tasks,
        "sessions": sessions,
        "preflight": preflight,
        "config_hash": config.config_hash,
    }
    return MappingProxyType(
        {
            "snapshot_id": deterministic_id(
                "prospective_shadow_dashboard_snapshot", (canonical_hash(identity),)
            ),
            "overall_status": overall,
            "plan_id": schedule.plan_id,
            "as_of": as_of,
            "symbols": symbols,
            "symbol_status": MappingProxyType(symbol_status),
            "completed_sessions": complete,
            "scheduled_sessions": len(schedule.sessions),
            "remaining_dates": remaining,
            "next_session": next_session,
            "today": current,
            "today_preflight": preflight,
            "tasks": tasks,
            "sessions": sessions,
            "totals": evidence["totals"],
            "unsafe_evidence": unsafe,
            "database_state": evidence["database_state"],
            "network_used": False,
            "credentials_loaded": False,
            "database_write_performed": False,
            "scheduler_modified": False,
            "broker_write_performed": False,
            "order_api_available": False,
            "release_authorized": False,
        }
    )


def _read_evidence(
    database: Path,
    schedule: ProspectiveShadowScheduleConfig,
    *,
    as_of: datetime,
    audit_delay_minutes: int,
) -> Mapping[str, object]:
    rows = {
        item.session_id: {
            "market_day": item.market_day,
            "session_id": item.session_id,
            "start": False,
            "post_close": False,
            "audit_status": _default_audit_status(
                item, schedule, as_of, audit_delay_minutes
            ),
            "worker_cycles": 0,
            "completed_bars_seen": 0,
            "decision_cycles": 0,
            "emitted_decisions": 0,
            "directional_decisions": 0,
            "staged_shadow_intents": 0,
            "paper_intents": 0,
            "incidents": 0,
        }
        for item in schedule.sessions
    }
    unsafe = False
    database_state = "NOT_CREATED"
    if database.exists():
        database_state = "READ_ONLY"
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
        try:
            tables = {
                str(item[0])
                for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            ids = tuple(rows)
            placeholders = ",".join("?" for _ in ids)
            if "paper_shadow_orchestration_receipts" in tables:
                for session_id, action, broker_write in connection.execute(
                    f"SELECT session_id,action,broker_write_performed "
                    f"FROM paper_shadow_orchestration_receipts "
                    f"WHERE plan_id=? AND session_id IN ({placeholders})",
                    (schedule.plan_id, *ids),
                ):
                    item = rows[str(session_id)]
                    if str(action) == "START":
                        item["start"] = True
                    elif str(action) == "POST_CLOSE":
                        item["post_close"] = True
                    unsafe = unsafe or int(broker_write) != 0
            if "paper_shadow_daily_audits" in tables:
                for session_id, status, broker_write in connection.execute(
                    f"SELECT session_id,status,broker_write_detected "
                    f"FROM paper_shadow_daily_audits "
                    f"WHERE plan_id=? AND session_id IN ({placeholders})",
                    (schedule.plan_id, *ids),
                ):
                    rows[str(session_id)]["audit_status"] = str(status)
                    unsafe = unsafe or int(broker_write) != 0 or status == "UNSAFE_EVIDENCE"
            _aggregate_cycles(connection, tables, rows, placeholders, ids)
            unsafe = unsafe or _unsafe_execution(connection, tables, placeholders, ids)
        finally:
            connection.close()
    sessions = tuple(MappingProxyType(item) for item in rows.values())
    totals = {
        name: sum(_int_value(item[name]) for item in rows.values())
        for name in (
            "worker_cycles",
            "completed_bars_seen",
            "decision_cycles",
            "emitted_decisions",
            "directional_decisions",
            "staged_shadow_intents",
            "paper_intents",
            "incidents",
        )
    }
    return MappingProxyType(
        {
            "database_state": database_state,
            "sessions": sessions,
            "totals": MappingProxyType(totals),
            "unsafe_evidence": unsafe,
        }
    )


def _aggregate_cycles(
    connection: sqlite3.Connection,
    tables: set[str],
    rows: dict[str, dict[str, object]],
    placeholders: str,
    ids: tuple[str, ...],
) -> None:
    if "webull_burn_in_worker_cycles" in tables:
        query = (
            "SELECT session_id,COUNT(*),COALESCE(SUM(completed_bars_seen),0) "
            "FROM webull_burn_in_worker_cycles "
            f"WHERE session_id IN ({placeholders}) GROUP BY session_id"
        )
        for session_id, cycles, bars in connection.execute(query, ids):
            rows[str(session_id)]["worker_cycles"] = int(cycles)
            rows[str(session_id)]["completed_bars_seen"] = int(bars)
    if "burn_in_shadow_decision_cycles" in tables:
        query = (
            "SELECT session_id,COUNT(*),COALESCE(SUM(emitted_decisions),0),"
            "COALESCE(SUM(directional_decisions),0),"
            "COALESCE(SUM(staged_shadow_intents),0) "
            "FROM burn_in_shadow_decision_cycles "
            f"WHERE session_id IN ({placeholders}) GROUP BY session_id"
        )
        for session_id, cycles, emitted, directional, intents in connection.execute(
            query, ids
        ):
            item = rows[str(session_id)]
            item["decision_cycles"] = int(cycles)
            item["emitted_decisions"] = int(emitted)
            item["directional_decisions"] = int(directional)
            item["staged_shadow_intents"] = int(intents)
    for table, key in (("paper_intents", "paper_intents"), ("paper_incidents", "incidents")):
        if table not in tables:
            continue
        query = (
            f"SELECT session_id,COUNT(*) FROM {table} "
            f"WHERE session_id IN ({placeholders}) GROUP BY session_id"
        )
        for session_id, count in connection.execute(query, ids):
            rows[str(session_id)][key] = int(count)


def _unsafe_execution(
    connection: sqlite3.Connection,
    tables: set[str],
    placeholders: str,
    ids: tuple[str, ...],
) -> bool:
    for table in ("paper_orders", "paper_fills"):
        if table not in tables:
            continue
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE session_id IN ({placeholders})",
            ids,
        ).fetchone()
        if count is not None and int(count[0]) > 0:
            return True
    return False


def _default_audit_status(
    item: ScheduledShadowSession,
    schedule: ProspectiveShadowScheduleConfig,
    as_of: datetime,
    audit_delay_minutes: int,
) -> str:
    due = item.collect_at + timedelta(
        minutes=schedule.completion_grace_minutes + audit_delay_minutes
    )
    return "MISSING_AUDIT" if as_of > due else "PENDING"


def _load_task_snapshot(
    path: Path, expected: tuple[str, ...]
) -> tuple[Mapping[str, object], ...]:
    if not path.exists():
        return tuple(
            MappingProxyType(
                {
                    "name": name,
                    "state": "MISSING",
                    "next_run_at": None,
                    "last_run_at": None,
                    "last_result": None,
                }
            )
            for name in expected
        )
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or set(raw) != {"captured_at", "tasks"}:
        raise ValueError("Phase 12F task snapshot keys are invalid")
    _parse_optional_time(raw["captured_at"], required=True)
    tasks = raw["tasks"]
    if not isinstance(tasks, list) or len(tasks) != len(expected):
        raise ValueError("Phase 12F task snapshot count is invalid")
    parsed: dict[str, Mapping[str, object]] = {}
    for item in tasks:
        if not isinstance(item, dict) or set(item) != {
            "name",
            "state",
            "next_run_at",
            "last_run_at",
            "last_result",
        }:
            raise ValueError("Phase 12F task snapshot item is invalid")
        name = item["name"]
        state = str(item["state"]).upper()
        result = item["last_result"]
        if (
            name not in expected
            or name in parsed
            or state not in {"READY", "RUNNING", "DISABLED", "MISSING", "UNKNOWN"}
            or isinstance(result, bool)
            or (result is not None and not isinstance(result, int))
        ):
            raise ValueError("Phase 12F task snapshot values are invalid")
        parsed[str(name)] = MappingProxyType(
            {
                "name": str(name),
                "state": state,
                "next_run_at": _parse_optional_time(item["next_run_at"]),
                "last_run_at": _parse_optional_time(item["last_run_at"]),
                "last_result": result,
            }
        )
    if set(parsed) != set(expected):
        raise ValueError("Phase 12F task snapshot names are invalid")
    return tuple(parsed[name] for name in expected)


def _preflight_status(
    root: Path,
    log_root: str,
    schedule: ProspectiveShadowScheduleConfig,
    as_of: datetime,
) -> str:
    market_day = as_of.astimezone(ZoneInfo("America/New_York")).date()
    scheduled = next(
        (item for item in schedule.sessions if item.market_day == market_day), None
    )
    if scheduled is None:
        return "NOT_SCHEDULED"
    path = _contained(root, log_root) / f"shadow-preflight-{market_day:%Y%m%d}.log"
    if path.exists():
        lines = tuple(line.strip() for line in path.read_text(encoding="utf-8").splitlines())
        if any(" READY " in f" {line} " for line in lines if line):
            return "READY"
        if any("NO_ACTION" in line for line in lines if line):
            return "NO_ACTION"
    return "MISSING" if as_of >= scheduled.open_at else "PENDING"


def _dashboard_html(snapshot: Mapping[str, object]) -> str:
    status = str(snapshot["overall_status"])
    status_class = status.lower()
    today = snapshot["today"]
    next_session = snapshot["next_session"]
    raw_tasks = snapshot["tasks"]
    raw_totals = snapshot["totals"]
    raw_symbol_status = snapshot["symbol_status"]
    raw_sessions = snapshot["sessions"]
    if (
        not isinstance(raw_tasks, tuple)
        or not isinstance(raw_totals, Mapping)
        or not isinstance(raw_symbol_status, Mapping)
        or not isinstance(raw_sessions, tuple)
    ):
        raise TypeError("validated Phase 12F dashboard values are invalid")
    tasks = cast(tuple[Mapping[str, object], ...], raw_tasks)
    totals = cast(Mapping[str, object], raw_totals)
    symbol_status = cast(Mapping[str, object], raw_symbol_status)
    sessions = cast(tuple[Mapping[str, object], ...], raw_sessions)
    if today is not None and not isinstance(today, Mapping):
        raise TypeError("validated Phase 12F current session is invalid")
    if next_session is not None and not isinstance(next_session, Mapping):
        raise TypeError("validated Phase 12F next session is invalid")
    completed = _int_value(snapshot["completed_sessions"])
    scheduled = _int_value(snapshot["scheduled_sessions"])
    progress = 100 * completed / scheduled
    remaining = snapshot["remaining_dates"]
    if not isinstance(remaining, tuple):
        raise TypeError("validated Phase 12F remaining dates are invalid")
    task_rows = "".join(
        _row(
            str(item["name"]).replace("Trading System - Phase 12E ", ""),
            f"{item['state']} · next {_display_time(item['next_run_at'])} · "
            f"last result {_display_value(item['last_result'])}",
        )
        for item in tasks
    )
    session_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['market_day']))}</td>"
        f"<td>{html.escape(str(item['audit_status']))}</td>"
        f"<td>{'YES' if item['start'] else 'NO'}</td>"
        f"<td>{'YES' if item['post_close'] else 'NO'}</td>"
        f"<td>{item['worker_cycles']}</td>"
        f"<td>{item['decision_cycles']}</td>"
        f"<td>{item['staged_shadow_intents']}</td>"
        "</tr>"
        for item in sessions
    )
    today_body = (
        "<p>No frozen session is scheduled today.</p>"
        if today is None
        else "".join(
            (
                _row("Session", str(today["session_id"])),
                _row("Preflight", str(snapshot["today_preflight"])),
                _row("Start receipt", "RECORDED" if today["start"] else "PENDING"),
                _row(
                    "Post-close receipt",
                    "RECORDED" if today["post_close"] else "PENDING",
                ),
                _row("Daily audit", str(today["audit_status"])),
            )
        )
    )
    next_value = "None" if next_session is None else str(next_session["market_day"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trading System - Burn-in Operations</title>
  <style>
    :root {{ color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #07111f; color: #edf3fb; }}
    main {{ width: min(1180px, calc(100% - 28px)); margin: 32px auto 64px; }}
    h1 {{ margin-bottom: 4px; font-size: clamp(2rem, 5vw, 3.3rem); }}
    .subtle {{ color: #9cb0c8; }}
    .hero, section {{ background: #101d2e; border: 1px solid #263a53;
      border-radius: 16px; padding: 20px; }}
    .hero {{ display: flex; justify-content: space-between; gap: 18px;
      align-items: center; margin: 22px 0; }}
    .badge {{ border-radius: 999px; padding: 10px 16px; font-weight: 800; }}
    .green {{ background: #123c30; color: #71e5ad; }}
    .amber {{ background: #4a3510; color: #ffd27d; }}
    .red {{ background: #4b1f25; color: #ff9aa6; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px; margin-bottom: 16px; }}
    dl {{ margin: 0; }}
    .row {{ display: flex; justify-content: space-between; gap: 14px;
      padding: 9px 0; border-bottom: 1px solid #263a53; }}
    .row:last-child {{ border-bottom: 0; }}
    dt {{ color: #aebdd1; }} dd {{ margin: 0; text-align: right; font-weight: 650; }}
    .progress {{ height: 12px; background: #263a53; border-radius: 999px; overflow: hidden; }}
    .progress span {{ display: block; height: 100%; background: #47c990;
      width: {progress:.1f}%; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
    th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #263a53; }}
    th {{ color: #9cb0c8; }}
    footer {{ margin-top: 18px; color: #8194ad; font-size: .9rem; }}
  </style>
</head>
<body><main>
  <header><h1>Burn-in operations</h1>
    <p class="subtle">Frozen Phase 12E cohort · offline, read-only evidence view</p></header>
  <div class="hero"><div><strong>Plan</strong><br>{html.escape(str(snapshot['plan_id']))}
    <p class="subtle">As of {html.escape(_display_time(snapshot['as_of']))}</p></div>
    <span class="badge {status_class}">{status}</span></div>
  <div class="grid">
    <section><h2>Cohort progress</h2>
      <p><strong>{completed} / {scheduled}</strong>
        sessions complete</p><div class="progress"><span></span></div>
      <dl>{_row('Next session', next_value)}
        {_row('Remaining dates', str(len(remaining)))}
        {_row('Database', str(snapshot['database_state']))}</dl></section>
    <section><h2>Today</h2><dl>{today_body}</dl></section>
    <section><h2>Market-data collection</h2><dl>
      {''.join(_row(str(symbol), str(state)) for symbol, state in symbol_status.items())}
      {_row('Worker cycles', str(totals['worker_cycles']))}
      {_row('Completed bars seen', str(totals['completed_bars_seen']))}</dl></section>
    <section><h2>Decision activity</h2><dl>
      {_row('Decision cycles', str(totals['decision_cycles']))}
      {_row('Emitted decisions', str(totals['emitted_decisions']))}
      {_row('Directional decisions', str(totals['directional_decisions']))}
      {_row('Staged shadow intents', str(totals['staged_shadow_intents']))}
      {_row('Persisted paper intents', str(totals['paper_intents']))}</dl></section>
    <section><h2>Windows task readiness</h2><dl>{task_rows}</dl></section>
    <section><h2>Safety boundary</h2><dl>
      {_row('Unsafe evidence', 'YES' if snapshot['unsafe_evidence'] else 'NO')}
      {_row('Incidents', str(totals['incidents']))}
      {_row('Broker writes', 'DISABLED')}
      {_row('Order API', 'DISABLED')}
      {_row('Live trading', 'DISABLED')}
      {_row('Automatic promotion', 'DISABLED')}</dl></section>
  </div>
  <section><h2>Session ledger</h2><div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Audit</th><th>Start</th><th>Close</th>
      <th>Worker</th><th>Decisions</th><th>Intents</th></tr></thead>
    <tbody>{session_rows}</tbody></table></div></section>
  <footer>Static local artifact · no scripts · no network · no credentials ·
    snapshot {html.escape(str(snapshot['snapshot_id']))}</footer>
</main></body></html>
"""


def _row(label: str, value: str) -> str:
    return (
        f'<div class="row"><dt>{html.escape(label)}</dt>'
        f"<dd>{html.escape(value)}</dd></div>"
    )


def _display_time(value: object) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo("America/New_York")).isoformat(
            timespec="minutes"
        )
    return str(value)


def _display_value(value: object) -> str:
    return "none" if value is None else str(value)


def _task_unhealthy(item: Mapping[str, object]) -> bool:
    state = item["state"]
    result = item["last_result"]
    if state == "READY":
        return result not in {None, 0, 267011}
    if state == "RUNNING":
        return result not in {None, 0, 267009}
    return True


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("validated Phase 12F integer is invalid")
    return value


def _date_value(value: object) -> date:
    if not isinstance(value, date):
        raise TypeError("validated Phase 12F date is invalid")
    return value


def _parse_optional_time(value: object, *, required: bool = False) -> datetime | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError("Phase 12F task timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Phase 12F task timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _contained(root: Path, value: object) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError("Phase 12F path must be text")
    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Phase 12F path escapes project root")
    return candidate


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
        and "\\" not in value
    )


def _require_utc(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 12F timestamps must be UTC")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
