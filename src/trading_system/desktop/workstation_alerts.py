"""Phase 11B read-only decision alerts for the local workstation."""

# HTML presentation is intentionally kept in this module for a self-contained artifact.
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

from trading_system.desktop import workstation as base
from trading_system.desktop.local_status import load_local_status_config
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class WorkstationAlertConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkstationAlertConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class DecisionAlert:
    alert_id: str
    decision_id: str
    run_id: str
    observation_id: str
    known_at: datetime
    symbol: str
    timeframe: str
    action: str
    direction: str
    confidence: Decimal
    setup_quality: Decimal
    entry_quality: Decimal
    reason_codes: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    planned_entry: Decimal | None = None
    initial_stop: Decimal | None = None
    reward_risk: Decimal | None = None
    runway_adr: Decimal | None = None

    def __post_init__(self) -> None:
        if (
            not all((self.alert_id, self.decision_id, self.run_id, self.observation_id))
            or self.known_at.tzinfo is None
            or self.known_at.utcoffset() != UTC.utcoffset(self.known_at)
            or not self.symbol
            or self.timeframe not in {"1w", "1d", "4h", "1h"}
            or self.action not in {"LONG", "SHORT", "WATCH", "NO_TRADE"}
            or self.direction not in {"LONG", "SHORT", "NONE"}
            or any(not value.is_finite() or value < 0 or value > 100 for value in self._scores())
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or self.missing_conditions != tuple(sorted(set(self.missing_conditions)))
            or self.rejection_reasons != tuple(sorted(set(self.rejection_reasons)))
            or any(value is not None and not value.is_finite() for value in self._plan_values())
        ):
            raise ValueError("invalid Phase 11B decision alert")
        directional = self.action in {"LONG", "SHORT"}
        if directional != (self.planned_entry is not None and self.initial_stop is not None):
            raise ValueError("invalid Phase 11B directional plan")
        if directional and self.direction != self.action:
            raise ValueError("invalid Phase 11B decision direction")
        if not directional and self.direction != "NONE":
            raise ValueError("invalid Phase 11B decision direction")
        if any(
            value is not None and value <= 0 for value in (self.planned_entry, self.initial_stop)
        ) or any(
            value is not None and value < 0 for value in (self.reward_risk, self.runway_adr)
        ):
            raise ValueError("invalid Phase 11B plan values")

    def _scores(self) -> tuple[Decimal, ...]:
        return self.confidence, self.setup_quality, self.entry_quality

    def _plan_values(self) -> tuple[Decimal | None, ...]:
        return self.planned_entry, self.initial_stop, self.reward_risk, self.runway_adr


@dataclass(frozen=True, slots=True)
class AlertWorkstationSnapshot:
    snapshot_id: str
    as_of: datetime
    base_snapshot: base.WorkstationSnapshot
    alerts: tuple[DecisionAlert, ...]
    config_hash: str
    version: str = "11B.1.0"
    read_only: bool = True
    network_used: bool = False
    credentials_loaded: bool = False
    database_write_performed: bool = False
    external_notification_sent: bool = False
    broker_write_performed: bool = False
    sandbox_execution_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.snapshot_id
            or self.as_of.tzinfo is None
            or self.as_of.utcoffset() != UTC.utcoffset(self.as_of)
            or self.base_snapshot.as_of != self.as_of
            or tuple(sorted(self.alerts, key=_alert_order)) != self.alerts
            or not self.config_hash.startswith("sha256:")
            or self.version != "11B.1.0"
            or not self.read_only
            or any(
                (
                    self.network_used,
                    self.credentials_loaded,
                    self.database_write_performed,
                    self.external_notification_sent,
                    self.broker_write_performed,
                    self.sandbox_execution_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11B workstation snapshot")


@dataclass(frozen=True, slots=True)
class AlertWorkstationArtifact:
    artifact_id: str
    output_path: str
    content_hash: str
    snapshot_id: str
    mode: str = "READ_ONLY_LOCAL_DECISION_ALERTS"
    network_used: bool = False
    external_notification_sent: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.artifact_id, self.output_path, self.snapshot_id))
            or not self.content_hash.startswith("sha256:")
            or self.mode != "READ_ONLY_LOCAL_DECISION_ALERTS"
            or any(
                (
                    self.network_used,
                    self.external_notification_sent,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 11B workstation artifact")


def load_alert_config(path: str | Path) -> WorkstationAlertConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "workstation_alert_version",
        "mode",
        "base_config",
        "output",
        "max_alerts",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise WorkstationAlertConfigError("Phase 11B configuration keys are invalid")
    authority = raw["authority"]
    authority_keys = {
        "database_write_enabled",
        "network_enabled",
        "credential_loading_enabled",
        "external_notifications_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        raw["workstation_alert_version"] != "11B.1.0"
        or raw["mode"] != "READ_ONLY_LOCAL_DECISION_ALERTS"
        or not _relative(raw["base_config"])
        or not _relative(raw["output"])
        or not str(raw["output"]).endswith(".html")
        or not isinstance(raw["max_alerts"], int)
        or not 1 <= raw["max_alerts"] <= 200
        or not isinstance(authority, dict)
        or set(authority) != authority_keys
        or any(value is not False for value in authority.values())
    ):
        raise WorkstationAlertConfigError("Phase 11B configuration is invalid or unsafe")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return WorkstationAlertConfig(MappingProxyType(frozen), canonical_hash(raw))


def inspect_alert_workstation(
    config: WorkstationAlertConfig,
    *,
    project_root: str | Path,
    as_of: datetime,
) -> AlertWorkstationSnapshot:
    if as_of.tzinfo is None or as_of.utcoffset() != UTC.utcoffset(as_of):
        raise ValueError("Phase 11B as_of must be UTC")
    root = Path(project_root).resolve()
    base_config = base.load_workstation_config(_contained(root, config.values["base_config"]))
    base_snapshot = base.inspect_workstation(base_config, project_root=root, as_of=as_of)
    local_config_path = _contained(root, base_config.values["local_status_config"])
    local_config = load_local_status_config(local_config_path)
    local_values = getattr(local_config, "values", None)
    if not isinstance(local_values, Mapping):
        raise TypeError("validated local status configuration is invalid")
    database = _contained(root, local_values["database"])
    maximum = config.values["max_alerts"]
    if not isinstance(maximum, int):
        raise TypeError("validated Phase 11B alert limit is invalid")
    alerts = _load_alerts(database, as_of=as_of, maximum=maximum)
    identity = (
        as_of,
        base_snapshot.snapshot_id,
        tuple(item.alert_id for item in alerts),
        config.config_hash,
    )
    return AlertWorkstationSnapshot(
        deterministic_id("alert_workstation_snapshot", identity),
        as_of,
        base_snapshot,
        alerts,
        config.config_hash,
    )


def render_alert_workstation(
    config: WorkstationAlertConfig,
    snapshot: AlertWorkstationSnapshot,
    *,
    project_root: str | Path,
) -> AlertWorkstationArtifact:
    root = Path(project_root).resolve()
    output = _contained(root, config.values["output"])
    base_config = base.load_workstation_config(_contained(root, config.values["base_config"]))
    display = base_config.values["display"]
    if not isinstance(display, Mapping):
        raise TypeError("validated workstation display is invalid")
    document = base._document(
        snapshot.base_snapshot,
        str(display["title"]),
        str(display["subtitle"]),
    )
    document = _inject_alerts(document, snapshot.alerts)
    content_hash = canonical_hash(document)
    artifact = AlertWorkstationArtifact(
        deterministic_id(
            "alert_workstation_artifact",
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


def _load_alerts(database: Path, *, as_of: datetime, maximum: int) -> tuple[DecisionAlert, ...]:
    if not database.is_file():
        return ()
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"decisions", "feature_snapshots", "candles"}.issubset(tables):
            return ()
        rows = connection.execute(
            "SELECT d.decision_id,d.run_id,d.observation_id,d.known_at,d.action,"
            "d.confidence,d.setup_quality,d.entry_quality,d.reason_codes_json,"
            "d.payload_json,d.payload_hash,c.symbol,c.timeframe "
            "FROM decisions d JOIN feature_snapshots f ON f.observation_id=d.observation_id "
            "JOIN candles c ON c.candle_id=f.candle_id WHERE d.known_at<=? "
            "ORDER BY d.known_at DESC,d.decision_id DESC",
            (as_of.isoformat(),),
        ).fetchall()
    finally:
        connection.close()
    latest: dict[tuple[str, str], DecisionAlert] = {}
    for row in rows:
        alert = _row_to_alert(row)
        latest.setdefault((alert.symbol, alert.timeframe), alert)
    return tuple(sorted(latest.values(), key=_alert_order)[:maximum])


def _row_to_alert(row: Sequence[object]) -> DecisionAlert:
    payload = json.loads(str(row[9]))
    if not isinstance(payload, dict) or canonical_hash(payload) != str(row[10]):
        raise ValueError("Phase 11B decision payload integrity check failed")
    action = str(row[4])
    if payload.get("action") != action:
        raise ValueError("Phase 11B decision action mismatch")
    known_at = _time(row[3])
    reason_codes = _strings(json.loads(str(row[8])))
    missing = _strings(payload.get("missing_conditions", []))
    rejected = _strings(payload.get("rejection_reasons", []))
    plan = payload.get("entry_plan")
    planned_entry: Decimal | None = None
    initial_stop: Decimal | None = None
    reward_risk: Decimal | None = None
    runway_adr: Decimal | None = None
    if isinstance(plan, dict):
        planned_entry = _canonical_decimal(plan.get("planned_entry"))
        initial_stop = _canonical_decimal(plan.get("initial_stop"))
        reward_risk = _canonical_decimal(plan.get("reward_risk"), optional=True)
        runway_adr = _canonical_decimal(plan.get("runway_adr"), optional=True)
    values = (row[0], row[1], row[2], known_at, row[11], row[12], action, row[5], reason_codes)
    return DecisionAlert(
        deterministic_id("decision_alert", values),
        str(row[0]),
        str(row[1]),
        str(row[2]),
        known_at,
        str(row[11]),
        str(row[12]),
        action,
        str(payload.get("direction", "NONE")),
        _decimal(row[5]),
        _decimal(row[6]),
        _decimal(row[7]),
        tuple(sorted(set(reason_codes))),
        tuple(sorted(set(missing))),
        tuple(sorted(set(rejected))),
        planned_entry,
        initial_stop,
        reward_risk,
        runway_adr,
    )


def _inject_alerts(document: str, alerts: Sequence[DecisionAlert]) -> str:
    css = """
    .alert-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:14px}
    .alert-list{display:grid;gap:10px}.alert-row{display:grid;grid-template-columns:90px 1fr 150px 130px;gap:14px;
      align-items:center;padding:14px;border:1px solid var(--line);border-radius:11px;background:#09141d}
    .alert-action{font-weight:900}.alert-row.long .alert-action,.alert-row.short .alert-action{color:var(--teal)}
    .alert-row.watch .alert-action{color:var(--amber)}.alert-row.no_trade .alert-action{color:var(--red)}
    .alert-reason{color:var(--muted);font-size:.8rem;margin-top:4px;overflow-wrap:anywhere}
    .alert-metric{text-align:right}.alert-empty{padding:32px;text-align:center;color:var(--muted)}
    @media(max-width:800px){.alert-summary{grid-template-columns:repeat(2,1fr)}.alert-row{grid-template-columns:1fr 1fr}
      .alert-metric{text-align:left}}
    """
    counts = {action: sum(item.action == action for item in alerts) for action in ("LONG", "SHORT", "WATCH", "NO_TRADE")}
    summary = "".join(
        f'<div class="card"><div class="label">{html.escape(label)}</div><div class="value">{counts[action]}</div></div>'
        for action, label in (("LONG", "Long"), ("SHORT", "Short"), ("WATCH", "Watch"), ("NO_TRADE", "No trade"))
    )
    rows = "".join(_alert_html(item) for item in alerts)
    if not rows:
        rows = '<div class="panel alert-empty">No causal decisions are stored yet. Alerts will appear after the deterministic engine records a decision.</div>'
    section = f"""
  <div class="section-title" id="alerts"><h2>Decision alerts</h2><span>Latest persisted decision per symbol and timeframe</span></div>
  <div class="alert-summary">{summary}</div><div class="alert-list">{rows}</div>
  <div class="panel" style="margin-top:14px"><p class="muted" style="margin:0">Local display only · No sound, email, text message, network call, credential access, or broker action.</p></div>
  """
    document = document.replace("</style>", css + "</style>")
    document = document.replace('<a href="#decisions">Decision engine</a>', '<a href="#alerts">Alerts</a><a href="#decisions">Decision engine</a>')
    return document.replace('  <div class="section-title" id="decisions">', section + '  <div class="section-title" id="decisions">')


def _alert_html(alert: DecisionAlert) -> str:
    reasons = alert.rejection_reasons or alert.missing_conditions or alert.reason_codes
    reason_text = " · ".join(reasons) if reasons else "No missing or rejection condition recorded"
    plan = ""
    if alert.planned_entry is not None and alert.initial_stop is not None:
        plan = f"Entry {alert.planned_entry} · Stop {alert.initial_stop}"
        if alert.reward_risk is not None:
            plan += f" · R:R {alert.reward_risk}"
    context = plan or reason_text
    return f"""<article class="alert-row {alert.action.lower()}">
      <div class="alert-action">{html.escape(alert.action)}</div>
      <div><strong>{html.escape(alert.symbol)} · {html.escape(alert.timeframe.upper())}</strong>
        <div class="alert-reason">{html.escape(context)}</div></div>
      <div class="alert-metric"><span class="label">Confidence</span><div>{alert.confidence}</div></div>
      <div class="alert-metric"><span class="label">Known at</span><div>{html.escape(alert.known_at.isoformat())}</div></div>
    </article>"""


def _alert_order(alert: DecisionAlert) -> tuple[float, str, str, str]:
    return (-alert.known_at.timestamp(), alert.symbol, alert.timeframe, alert.decision_id)


def _time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Phase 11B decision time is invalid")
    return parsed.astimezone(UTC)


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Phase 11B decision number is invalid") from exc
    if not result.is_finite():
        raise ValueError("Phase 11B decision number is invalid")
    return result


def _canonical_decimal(value: object, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    if not isinstance(value, dict) or set(value) != {"__decimal__"}:
        raise ValueError("Phase 11B plan number is invalid")
    return _decimal(value["__decimal__"])


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError("Phase 11B reason collection is invalid")
    return tuple(str(item) for item in value)


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _contained(root: Path, value: object) -> Path:
    if not _relative(value):
        raise WorkstationAlertConfigError("Phase 11B path is invalid")
    path = (root / str(value)).resolve()
    if root not in path.parents:
        raise WorkstationAlertConfigError("Phase 11B path escapes project root")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render local read-only decision alerts")
    parser.add_argument("--config", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args(argv)
    as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00")).astimezone(UTC)
    config = load_alert_config(args.config)
    snapshot = inspect_alert_workstation(config, project_root=args.project_root, as_of=as_of)
    artifact = render_alert_workstation(config, snapshot, project_root=args.project_root)
    print(canonical_json(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
