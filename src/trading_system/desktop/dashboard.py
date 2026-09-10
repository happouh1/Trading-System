"""Deterministic, offline Phase 9H operator dashboard rendering."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.desktop.launcher import DesktopLaunchStatus
from trading_system.serialization import canonical_hash, deterministic_id


class DesktopDashboardConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DesktopDashboardConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class DesktopDashboardArtifact:
    artifact_id: str
    output_path: str
    content_hash: str
    status_id: str
    mode: str = "READ_ONLY_LOCAL_DASHBOARD"
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    scheduler_started: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.artifact_id
            or not self.output_path
            or not self.content_hash.startswith("sha256:")
            or not self.status_id
            or self.mode != "READ_ONLY_LOCAL_DASHBOARD"
            or self.network_used
            or self.credentials_loaded
            or self.broker_write_performed
            or self.scheduler_started
            or self.sandbox_execution_enabled
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9H dashboard artifact")


def load_desktop_dashboard_config(path: str | Path) -> DesktopDashboardConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "dashboard_version",
        "mode",
        "operator_config",
        "output",
        "display",
        "authority",
    }:
        raise DesktopDashboardConfigError("Phase 9H configuration keys are invalid")
    if raw["dashboard_version"] != "9H.1.0" or raw["mode"] != "READ_ONLY_LOCAL_DASHBOARD":
        raise DesktopDashboardConfigError("Phase 9H mode is invalid")
    if not _canonical_relative_path(raw["operator_config"]):
        raise DesktopDashboardConfigError("Phase 9H operator config path is invalid")
    if not _canonical_relative_path(raw["output"]) or not str(raw["output"]).endswith(".html"):
        raise DesktopDashboardConfigError("Phase 9H output path is invalid")
    if raw["display"] != {"title": "Trading System", "subtitle": "Operator Home"}:
        raise DesktopDashboardConfigError("Phase 9H display settings are invalid")
    authority = raw["authority"]
    expected_authority = {
        "process_scheduler_enabled",
        "network_enabled",
        "credential_loading_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise DesktopDashboardConfigError("Phase 9H authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return DesktopDashboardConfig(MappingProxyType(frozen), canonical_hash(raw))


def render_desktop_dashboard(
    config: DesktopDashboardConfig,
    status: DesktopLaunchStatus,
    *,
    project_root: str | Path,
) -> DesktopDashboardArtifact:
    root = Path(project_root).resolve()
    output_value = config.values["output"]
    display = config.values["display"]
    if not isinstance(output_value, str) or not isinstance(display, Mapping):
        raise TypeError("validated Phase 9H values have invalid types")
    output_path = (root / output_value).resolve()
    if root not in output_path.parents:
        raise DesktopDashboardConfigError("Phase 9H output escapes the project root")
    content = _dashboard_html(status, str(display["title"]), str(display["subtitle"]))
    content_hash = canonical_hash(content)
    identity = (status.status_id, config.config_hash, output_value, content_hash)
    artifact = DesktopDashboardArtifact(
        deterministic_id("desktop_dashboard_artifact", identity),
        str(output_path),
        content_hash,
        status.status_id,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(output_path)
    return artifact


def _dashboard_html(status: DesktopLaunchStatus, title: str, subtitle: str) -> str:
    ready = status.operator_home_ready
    readiness = "READY" if ready else "NEEDS ATTENTION"
    readiness_class = "ready" if ready else "attention"
    component_rows = "\n".join(
        "        <li><span>"
        + html.escape(name.replace("_", " ").title())
        + "</span><strong>"
        + ("MISSING" if name in status.missing_paths else "READY")
        + "</strong></li>"
        for name, _ in status.required_paths
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - {html.escape(subtitle)}</title>
  <style>
    :root {{ color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #07111f; color: #e7edf6; }}
    main {{ width: min(920px, calc(100% - 32px)); margin: 48px auto; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 5vw, 3.5rem); }}
    header p {{ color: #9fb0c8; font-size: 1.15rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 18px; }}
    section {{ background: #101d2e; border: 1px solid #263a53; border-radius: 16px; padding: 22px; }}
    .badge {{ display: inline-block; border-radius: 999px; padding: 7px 11px; font-weight: 700; }}
    .ready {{ color: #71e5ad; background: #123c30; }}
    .attention {{ color: #ffd27d; background: #4a3510; }}
    ul {{ list-style: none; margin: 12px 0 0; padding: 0; }}
    li {{ display: flex; justify-content: space-between; gap: 14px; padding: 10px 0; border-bottom: 1px solid #263a53; }}
    li:last-child {{ border-bottom: 0; }}
    .disabled {{ color: #71e5ad; }}
    footer {{ margin-top: 22px; color: #8194ad; font-size: .9rem; }}
  </style>
</head>
<body>
  <main>
    <header><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></header>
    <div class="grid">
      <section><h2>System readiness</h2><p class="badge {readiness_class}">{readiness}</p>
        <ul>
{component_rows}
        </ul>
      </section>
      <section><h2>Safety controls</h2>
        <ul>
          <li><span>Trading</span><strong class="disabled">DISABLED</strong></li>
          <li><span>Broker writes</span><strong class="disabled">DISABLED</strong></li>
          <li><span>Network access</span><strong class="disabled">DISABLED</strong></li>
          <li><span>Credential loading</span><strong class="disabled">DISABLED</strong></li>
          <li><span>Scheduler</span><strong class="disabled">DISABLED</strong></li>
        </ul>
      </section>
    </div>
    <footer>Read-only local dashboard | Status {html.escape(status.status_id)}</footer>
  </main>
</body>
</html>
"""


def _canonical_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts
