"""Phase 11A deterministic, read-only local trading workstation."""

# The self-contained HTML/CSS template intentionally keeps some presentation lines together.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.launcher import inspect_desktop_launcher, load_desktop_launch_config
from trading_system.desktop.local_status import inspect_local_operations, load_local_status_config
from trading_system.desktop.prospective_burn_in import (
    build_prospective_burn_in_plan,
    evaluate_prospective_burn_in,
    load_operator_request,
    load_prospective_burn_in_config,
    load_prospective_burn_in_observations,
)
from trading_system.desktop.release_audit import audit_release_readiness, load_release_audit_config
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class WorkstationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkstationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class WorkstationBar:
    candle_id: str
    symbol: str
    timeframe: str
    close_time: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    def __post_init__(self) -> None:
        if (
            not all((self.candle_id, self.symbol, self.timeframe, self.close_time))
            or min(self.open, self.high, self.low, self.close) <= 0
            or self.high < max(self.open, self.close)
            or self.low > min(self.open, self.close)
        ):
            raise ValueError("invalid Phase 11A workstation bar")


@dataclass(frozen=True, slots=True)
class WorkstationChart:
    symbol: str
    timeframe: str
    bars: tuple[WorkstationBar, ...]

    def __post_init__(self) -> None:
        if (
            not self.symbol
            or self.timeframe not in {"1W", "1D", "4H", "1H"}
            or any(
                item.symbol != self.symbol or item.timeframe != self.timeframe for item in self.bars
            )
            or tuple(sorted(self.bars, key=lambda item: (item.close_time, item.candle_id)))
            != self.bars
        ):
            raise ValueError("invalid Phase 11A workstation chart")


@dataclass(frozen=True, slots=True)
class WorkstationSnapshot:
    snapshot_id: str
    as_of: datetime
    release_state: str
    installation_state: str
    database_state: str
    runtime_state: str
    operator_health: str
    session_id: str | None
    incident_count: int
    unmatched_reconciliation_count: int
    burn_in_state: str
    burn_in_plan_id: str | None
    burn_in_window_start: str | None
    burn_in_window_end: str | None
    completed_sessions: int
    required_sessions: int
    completed_market_days: int
    required_market_days: int
    completed_trades: int
    required_trades: int
    rejection_fraction: Decimal
    maximum_rejection_fraction: Decimal
    burn_in_reason_codes: tuple[str, ...]
    charts: tuple[WorkstationChart, ...]
    config_hash: str
    workstation_version: str = "11A.1.0"
    read_only: bool = True
    database_write_performed: bool = False
    scheduler_started: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.snapshot_id
            or self.as_of.tzinfo is None
            or self.as_of.utcoffset() != UTC.utcoffset(self.as_of)
            or not all((self.release_state, self.installation_state, self.database_state))
            or min(
                self.incident_count,
                self.unmatched_reconciliation_count,
                self.completed_sessions,
                self.required_sessions,
                self.completed_market_days,
                self.required_market_days,
                self.completed_trades,
                self.required_trades,
            )
            < 0
            or not Decimal(0) <= self.rejection_fraction <= Decimal(1)
            or not Decimal(0) <= self.maximum_rejection_fraction <= Decimal(1)
            or self.burn_in_reason_codes != tuple(sorted(set(self.burn_in_reason_codes)))
            or tuple(sorted(self.charts, key=lambda item: (item.symbol, item.timeframe)))
            != self.charts
            or not self.config_hash.startswith("sha256:")
            or self.workstation_version != "11A.1.0"
            or not self.read_only
            or any(
                (
                    self.database_write_performed,
                    self.scheduler_started,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11A workstation snapshot")


@dataclass(frozen=True, slots=True)
class WorkstationArtifact:
    artifact_id: str
    output_path: str
    content_hash: str
    snapshot_id: str
    mode: str = "READ_ONLY_LOCAL_WORKSTATION"
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    scheduler_started: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.artifact_id, self.output_path, self.snapshot_id))
            or not self.content_hash.startswith("sha256:")
            or self.mode != "READ_ONLY_LOCAL_WORKSTATION"
            or any(
                (
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.scheduler_started,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11A workstation artifact")


def load_workstation_config(path: str | Path) -> WorkstationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "workstation_version",
        "mode",
        "launcher_config",
        "local_status_config",
        "release_config",
        "burn_in_config",
        "burn_in_request",
        "burn_in_evidence",
        "output",
        "display",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise WorkstationConfigError("Phase 11A configuration keys are invalid")
    path_keys = expected - {"workstation_version", "mode", "display", "authority"}
    if (
        raw["workstation_version"] != "11A.1.0"
        or raw["mode"] != "READ_ONLY_LOCAL_WORKSTATION"
        or any(not _relative(raw[key]) for key in path_keys)
        or not str(raw["output"]).endswith(".html")
    ):
        raise WorkstationConfigError("Phase 11A mode or paths are invalid")
    display = raw["display"]
    if not isinstance(display, dict) or set(display) != {
        "title",
        "subtitle",
        "symbols",
        "timeframes",
    }:
        raise WorkstationConfigError("Phase 11A display configuration is invalid")
    symbols = display["symbols"]
    timeframes = display["timeframes"]
    if (
        display["title"] != "Trading System"
        or not isinstance(display["subtitle"], str)
        or not isinstance(symbols, list)
        or symbols != sorted(set(symbols))
        or not symbols
        or not all(isinstance(value, str) and value.isalnum() for value in symbols)
        or timeframes != ["1W", "1D", "4H", "1H"]
    ):
        raise WorkstationConfigError("Phase 11A display values are invalid")
    authority = raw["authority"]
    authority_keys = {
        "database_write_enabled",
        "process_scheduler_enabled",
        "network_enabled",
        "credential_loading_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != authority_keys
        or any(value is not False for value in authority.values())
    ):
        raise WorkstationConfigError("Phase 11A authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return WorkstationConfig(MappingProxyType(frozen), canonical_hash(raw))


def inspect_workstation(
    config: WorkstationConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
) -> WorkstationSnapshot:
    if as_of.tzinfo is None or as_of.utcoffset() != UTC.utcoffset(as_of):
        raise ValueError("Phase 11A as_of must be UTC")
    root = Path(project_root).resolve()
    paths = {
        name: _contained(root, config.values[name])
        for name in (
            "launcher_config",
            "local_status_config",
            "release_config",
            "burn_in_config",
            "burn_in_request",
            "burn_in_evidence",
        )
    }
    launch = inspect_desktop_launcher(
        load_desktop_launch_config(paths["launcher_config"]), project_root=root
    )
    local_config = load_local_status_config(paths["local_status_config"])
    operations = inspect_local_operations(local_config, project_root=root)
    release = audit_release_readiness(
        load_release_audit_config(paths["release_config"]), project_root=root
    )
    plan_id: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    completed_sessions = 0
    required_sessions = 0
    completed_days = 0
    required_days = 0
    completed_trades = 0
    required_trades = 0
    rejection_fraction = Decimal(0)
    maximum_rejection_fraction = Decimal(0)
    reasons: tuple[str, ...] = ("BURN_IN_REQUEST_MISSING",)
    burn_state = "NOT_REGISTERED"
    if paths["burn_in_request"].is_file():
        plan = build_prospective_burn_in_plan(
            load_prospective_burn_in_config(paths["burn_in_config"]),
            release,
            load_operator_request(paths["burn_in_request"]),
        )
        observations = (
            load_prospective_burn_in_observations(paths["burn_in_evidence"])
            if paths["burn_in_evidence"].is_file()
            else ()
        )
        assessment = evaluate_prospective_burn_in(plan, observations, evaluated_at=as_of)
        plan_id = plan.plan_id
        window_start = plan.window_start.isoformat()
        window_end = plan.window_end.isoformat()
        completed_sessions = assessment.session_count
        required_sessions = plan.minimum_sessions
        completed_days = assessment.market_day_count
        required_days = plan.minimum_market_days
        completed_trades = assessment.completed_trade_count
        required_trades = plan.minimum_completed_trades
        rejection_fraction = assessment.rejection_fraction
        maximum_rejection_fraction = plan.maximum_rejection_fraction
        reasons = assessment.reason_codes
        burn_state = "PLANNED" if as_of < plan.window_start else assessment.state.value
    charts = _load_charts(config, local_config, root=root, as_of=as_of)
    values = (
        as_of,
        release.state.value,
        "READY" if launch.operator_home_ready else "NEEDS_ATTENTION",
        operations.status_id,
        burn_state,
        plan_id,
        completed_sessions,
        completed_days,
        completed_trades,
        rejection_fraction,
        reasons,
        tuple(
            (item.symbol, item.timeframe, tuple(bar.candle_id for bar in item.bars))
            for item in charts
        ),
        config.config_hash,
    )
    return WorkstationSnapshot(
        deterministic_id("workstation_snapshot", values),
        as_of,
        release.state.value,
        "READY" if launch.operator_home_ready else "NEEDS_ATTENTION",
        operations.database_state,
        operations.runtime_state,
        operations.operator_health,
        operations.session_id,
        operations.incident_count,
        operations.unmatched_reconciliation_count,
        burn_state,
        plan_id,
        window_start,
        window_end,
        completed_sessions,
        required_sessions,
        completed_days,
        required_days,
        completed_trades,
        required_trades,
        rejection_fraction,
        maximum_rejection_fraction,
        reasons,
        charts,
        config.config_hash,
    )


def render_workstation(
    config: WorkstationConfig,
    snapshot: WorkstationSnapshot,
    *,
    project_root: str | Path,
) -> WorkstationArtifact:
    root = Path(project_root).resolve()
    output = _contained(root, config.values["output"])
    display = config.values["display"]
    if not isinstance(display, Mapping):
        raise TypeError("validated Phase 11A display must be a mapping")
    document = _document(snapshot, str(display["title"]), str(display["subtitle"]))
    content_hash = canonical_hash(document)
    artifact = WorkstationArtifact(
        deterministic_id(
            "workstation_artifact",
            (
                snapshot.snapshot_id,
                config.config_hash,
                output.relative_to(root).as_posix(),
                content_hash,
            ),
        ),
        str(output),
        content_hash,
        snapshot.snapshot_id,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(document, encoding="utf-8", newline="\n")
    temporary.replace(output)
    return artifact


def _load_charts(
    config: WorkstationConfig,
    local_config: object,
    *,
    root: Path,
    as_of: datetime,
) -> tuple[WorkstationChart, ...]:
    values = getattr(local_config, "values", None)
    if not isinstance(values, Mapping):
        raise TypeError("validated local status configuration is invalid")
    database = _contained(root, values["database"])
    display = config.values["display"]
    if not isinstance(display, Mapping):
        raise TypeError("validated Phase 11A display must be a mapping")
    symbols = _strings(display["symbols"])
    timeframes = _strings(display["timeframes"])
    empty = tuple(
        sorted(
            (
                WorkstationChart(symbol, timeframe, ())
                for symbol in symbols
                for timeframe in timeframes
            ),
            key=lambda item: (item.symbol, item.timeframe),
        )
    )
    if not database.is_file():
        return empty
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "candles" not in tables:
            return empty
        mapping = {"1W": "1w", "1D": "1d", "4H": "4h", "1H": "1h"}
        charts = []
        for symbol in symbols:
            for timeframe in timeframes:
                rows = connection.execute(
                    "SELECT candle_id, close_time, open, high, low, close "
                    "FROM candles WHERE symbol=? AND timeframe=? AND is_complete=1 "
                    "AND close_time<=? ORDER BY close_time DESC, candle_id DESC LIMIT 96",
                    (symbol, mapping[timeframe], as_of.isoformat()),
                ).fetchall()
                unique: dict[str, WorkstationBar] = {}
                for row in rows:
                    close_time = str(row[1])
                    unique.setdefault(
                        close_time,
                        WorkstationBar(
                            str(row[0]),
                            symbol,
                            timeframe,
                            close_time,
                            _decimal(row[2]),
                            _decimal(row[3]),
                            _decimal(row[4]),
                            _decimal(row[5]),
                        ),
                    )
                bars = tuple(
                    sorted(unique.values(), key=lambda item: (item.close_time, item.candle_id))[
                        -48:
                    ]
                )
                charts.append(WorkstationChart(symbol, timeframe, bars))
        return tuple(sorted(charts, key=lambda item: (item.symbol, item.timeframe)))
    finally:
        connection.close()


def _document(snapshot: WorkstationSnapshot, title: str, subtitle: str) -> str:
    plan_badge = "positive" if snapshot.burn_in_state in {"PASS", "ACTIVE"} else "warning"
    release_badge = "positive" if snapshot.release_state.startswith("READY") else "danger"
    reasons = ", ".join(snapshot.burn_in_reason_codes) or "None"
    chart_sections = "\n".join(
        _symbol_section(symbol, snapshot.charts)
        for symbol in sorted({item.symbol for item in snapshot.charts})
    )
    session = snapshot.session_id or "No session recorded"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} — Workstation</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, "Segoe UI", sans-serif; --bg:#071018;
      --panel:#0d1924; --panel2:#111f2c; --line:#223446; --text:#e9f0f6; --muted:#8fa4b8;
      --teal:#42d6b0; --amber:#f0b35a; --red:#ff6b75; --blue:#68a9ff; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--text); }}
    .shell {{ display:grid; grid-template-columns:230px minmax(0,1fr); min-height:100vh; }}
    aside {{ border-right:1px solid var(--line); padding:28px 20px; background:#09141e; position:sticky;
      top:0; height:100vh; }} .brand {{ font-size:1.15rem; font-weight:800; letter-spacing:.02em; }}
    .mode {{ color:var(--teal); font-size:.72rem; font-weight:800; margin-top:7px; }}
    nav {{ margin-top:36px; display:grid; gap:8px; }} nav a {{ color:var(--muted); text-decoration:none;
      padding:10px 12px; border-radius:9px; }} nav a:hover {{ color:var(--text); background:var(--panel2); }}
    aside footer {{ position:absolute; left:20px; bottom:24px; color:var(--muted); font-size:.75rem; }}
    main {{ padding:30px; max-width:1560px; width:100%; margin:auto; }}
    header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-bottom:24px; }}
    h1 {{ margin:0; font-size:clamp(1.8rem,4vw,3rem); }} header p {{ color:var(--muted); margin:.5rem 0 0; }}
    .asof {{ text-align:right; color:var(--muted); font-size:.8rem; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }}
    .card,.panel {{ background:linear-gradient(145deg,var(--panel2),var(--panel)); border:1px solid var(--line);
      border-radius:14px; padding:17px; box-shadow:0 14px 35px rgba(0,0,0,.15); }}
    .label {{ color:var(--muted); font-size:.72rem; font-weight:800; text-transform:uppercase;
      letter-spacing:.08em; }} .value {{ font-size:1.2rem; font-weight:800; margin-top:8px; overflow-wrap:anywhere; }}
    .badge {{ display:inline-block; margin-top:8px; padding:5px 9px; border-radius:999px; font-size:.72rem;
      font-weight:900; }} .positive {{ background:#103b32; color:var(--teal); }}
    .warning {{ background:#3b2b13; color:var(--amber); }} .danger {{ background:#3d1920; color:var(--red); }}
    .section-title {{ margin:34px 0 13px; display:flex; align-items:end; justify-content:space-between; }}
    .section-title h2 {{ margin:0; }} .section-title span {{ color:var(--muted); font-size:.82rem; }}
    .progress-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
    .meter {{ height:8px; background:#1a2a39; border-radius:20px; overflow:hidden; margin-top:12px; }}
    .meter span {{ display:block; height:100%; background:linear-gradient(90deg,var(--blue),var(--teal)); }}
    .chart-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    .chart-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
    .chart-head strong {{ font-size:.95rem; }} .last {{ color:var(--muted); font-size:.78rem; }}
    svg {{ width:100%; height:185px; display:block; background:#09141d; border-radius:10px; }}
    .empty {{ height:185px; display:grid; place-items:center; background:#09141d; color:var(--muted);
      border-radius:10px; text-align:center; padding:18px; }}
    .details {{ display:grid; grid-template-columns:1.2fr .8fr; gap:14px; }}
    ul {{ list-style:none; padding:0; margin:12px 0 0; }} li {{ display:flex; justify-content:space-between;
      gap:16px; padding:9px 0; border-bottom:1px solid var(--line); }} li:last-child {{ border-bottom:0; }}
    .muted {{ color:var(--muted); }} .safety {{ color:var(--teal); font-weight:800; }}
    @media(max-width:980px) {{ .shell{{grid-template-columns:1fr}} aside{{position:static;height:auto;border-right:0;
      border-bottom:1px solid var(--line)}} aside footer{{display:none}} nav{{display:flex;overflow:auto;margin-top:18px}}
      .cards{{grid-template-columns:repeat(2,1fr)}} }}
    @media(max-width:650px) {{ main{{padding:18px}} .cards,.progress-grid,.chart-grid,.details{{grid-template-columns:1fr}}
      header{{display:block}} .asof{{text-align:left;margin-top:12px}} }}
  </style>
</head>
<body><div class="shell">
  <aside><div class="brand">{html.escape(title)}</div><div class="mode">SANDBOX · READ ONLY</div>
    <nav><a href="#overview">Overview</a><a href="#burn-in">Burn-in</a><a href="#charts">Charts</a>
      <a href="#decisions">Decision engine</a><a href="#operations">Operations</a></nav>
    <footer>Live trading disabled<br>Broker writes disabled</footer>
  </aside>
  <main><header id="overview"><div><h1>{html.escape(subtitle)}</h1>
    <p>One causal view of market structure, decisions, and supervised sandbox evidence.</p></div>
    <div class="asof">As of<br><strong>{html.escape(snapshot.as_of.isoformat())}</strong></div></header>
  <div class="cards">
    <div class="card"><div class="label">Release audit</div><div class="value">{html.escape(snapshot.release_state)}</div>
      <span class="badge {release_badge}">{html.escape(snapshot.installation_state)}</span></div>
    <div class="card"><div class="label">Sandbox burn-in</div><div class="value">{html.escape(snapshot.burn_in_state)}</div>
      <span class="badge {plan_badge}">SUPERVISED</span></div>
    <div class="card"><div class="label">Paper runtime</div><div class="value">{html.escape(snapshot.runtime_state)}</div>
      <span class="badge warning">{html.escape(snapshot.operator_health)}</span></div>
    <div class="card"><div class="label">Final gate</div><div class="value">BLOCKED</div>
      <span class="badge warning">PENDING BURN-IN</span></div>
  </div>
  <div class="section-title" id="burn-in"><h2>Prospective sandbox burn-in</h2>
    <span>{html.escape(snapshot.burn_in_window_start or "Not registered")} → {html.escape(snapshot.burn_in_window_end or "Not registered")}</span></div>
  <div class="progress-grid">
    {_progress("Sessions", snapshot.completed_sessions, snapshot.required_sessions)}
    {_progress("Market days", snapshot.completed_market_days, snapshot.required_market_days)}
    {_progress("Completed trades", snapshot.completed_trades, snapshot.required_trades)}
  </div>
  <div class="panel" style="margin-top:14px"><div class="label">Plan identity</div>
    <div class="value">{html.escape(snapshot.burn_in_plan_id or "Not registered")}</div>
    <p class="muted">Rejection rate: {snapshot.rejection_fraction:.2%} / {snapshot.maximum_rejection_fraction:.2%} maximum · Reasons: {html.escape(reasons)}</p></div>
  <div class="section-title" id="charts"><h2>Multi-timeframe charts</h2><span>Completed candles only</span></div>
  {chart_sections}
  <div class="section-title" id="decisions"><h2>Decision engine</h2><span>Context → setup → trigger → risk</span></div>
  <div class="details"><div class="panel"><div class="label">Timeframe roles</div><ul>
    <li><span>Weekly</span><strong>Primary regime · 35%</strong></li><li><span>Daily</span><strong>Strategic context · 35%</strong></li>
    <li><span>4 Hour</span><strong>Setup formation · 20%</strong></li><li><span>1 Hour</span><strong>Trigger timing · 10%</strong></li></ul></div>
    <div class="panel"><div class="label">Decision states</div><ul><li><span>Directional</span><strong>LONG / SHORT</strong></li>
      <li><span>Developing</span><strong>WATCH</strong></li><li><span>Rejected</span><strong>NO TRADE + REASON</strong></li>
      <li><span>Image recognition</span><strong>NOT USED</strong></li></ul></div></div>
  <div class="section-title" id="operations"><h2>Operations and safety</h2><span>{html.escape(session)}</span></div>
  <div class="details"><div class="panel"><ul><li><span>Database</span><strong>{html.escape(snapshot.database_state)}</strong></li>
    <li><span>Incidents</span><strong>{snapshot.incident_count}</strong></li><li><span>Unmatched reconciliations</span>
    <strong>{snapshot.unmatched_reconciliation_count}</strong></li></ul></div>
    <div class="panel"><ul><li><span>Network use by UI</span><strong class="safety">NONE</strong></li>
    <li><span>Broker writes by UI</span><strong class="safety">DISABLED</strong></li>
    <li><span>Live trading</span><strong class="safety">DISABLED</strong></li></ul></div></div>
  </main></div></body></html>
"""


def _progress(label: str, actual: int, required: int) -> str:
    percent = 0 if required <= 0 else min(100, round(100 * actual / required))
    return f"""<div class="panel"><div class="label">{html.escape(label)}</div>
      <div class="value">{actual} / {required}</div><div class="meter" aria-label="{html.escape(label)} progress">
      <span style="width:{percent}%"></span></div></div>"""


def _symbol_section(symbol: str, charts: Sequence[WorkstationChart]) -> str:
    panels = "\n".join(
        _chart(item)
        for item in sorted(
            (value for value in charts if value.symbol == symbol),
            key=lambda item: ("1W", "1D", "4H", "1H").index(item.timeframe),
        )
    )
    return f"""<section aria-labelledby="symbol-{html.escape(symbol)}" style="padding:0;background:none;border:0;margin-bottom:22px">
    <div class="section-title"><h3 id="symbol-{html.escape(symbol)}">{html.escape(symbol)}</h3><span>Weekly · Daily · 4H · 1H</span></div>
    <div class="chart-grid">{panels}</div></section>"""


def _chart(chart: WorkstationChart) -> str:
    if not chart.bars:
        graphic = (
            '<div class="empty">No completed local candles available for this timeframe.</div>'
        )
        last = "Awaiting data"
    else:
        graphic = _candles_svg(chart.bars)
        last = f"Last {chart.bars[-1].close}"
    return f"""<div class="panel"><div class="chart-head"><strong>{html.escape(chart.timeframe)}</strong>
      <span class="last">{html.escape(last)}</span></div>{graphic}</div>"""


def _candles_svg(bars: Sequence[WorkstationBar]) -> str:
    width, height, padding = 520.0, 180.0, 14.0
    minimum = min(item.low for item in bars)
    maximum = max(item.high for item in bars)
    spread = maximum - minimum or Decimal(1)

    def y(value: Decimal) -> float:
        return padding + float((maximum - value) / spread) * (height - 2 * padding)

    step = (width - 2 * padding) / max(len(bars), 1)
    body_width = max(2.0, min(8.0, step * 0.58))
    marks = []
    for index, item in enumerate(bars):
        x = padding + step * (index + 0.5)
        color = "#42d6b0" if item.close >= item.open else "#ff6b75"
        high_y, low_y, open_y, close_y = y(item.high), y(item.low), y(item.open), y(item.close)
        top = min(open_y, close_y)
        body_height = max(1.5, abs(open_y - close_y))
        marks.append(
            f'<line x1="{x:.2f}" y1="{high_y:.2f}" x2="{x:.2f}" y2="{low_y:.2f}" '
            f'stroke="{color}" stroke-width="1"/><rect x="{x - body_width / 2:.2f}" y="{top:.2f}" '
            f'width="{body_width:.2f}" height="{body_height:.2f}" fill="{color}" rx="0.7"/>'
        )
    return (
        '<svg viewBox="0 0 520 180" role="img" aria-label="Completed candle chart">'
        '<path d="M14 45H506M14 90H506M14 135H506" stroke="#172838" stroke-width="1"/>'
        + "".join(marks)
        + "</svg>"
    )


def _contained(root: Path, value: object) -> Path:
    if not _relative(value):
        raise WorkstationConfigError("Phase 11A path is invalid")
    path = (root / str(value)).resolve()
    if root not in path.parents:
        raise WorkstationConfigError("Phase 11A path escapes project root")
    return path


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError("validated Phase 11A collection is invalid")
    result = tuple(str(item) for item in value)
    if not result or any(not item for item in result):
        raise TypeError("validated Phase 11A collection is invalid")
    return result


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid Phase 11A candle value") from exc
    if not result.is_finite():
        raise ValueError("invalid Phase 11A candle value")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the read-only Trading System workstation")
    parser.add_argument("--config", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00")).astimezone(UTC)
    config = load_workstation_config(args.config)
    snapshot = inspect_workstation(config, project_root=args.project_root, as_of=as_of)
    artifact = render_workstation(config, snapshot, project_root=args.project_root)
    print(canonical_json(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
