"""Phase 12G read-only launcher readiness for the burn-in operations page."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class ProspectiveShadowLauncherConfigError(ValueError):
    """The Phase 12G launcher configuration is malformed or unsafe."""


@dataclass(frozen=True, slots=True)
class ProspectiveShadowLauncherConfig:
    python: str
    dashboard_config: str
    render_script: str
    output: str
    shortcut_name: str
    config_hash: str
    launcher_version: str = "12G.1.0"


@dataclass(frozen=True, slots=True)
class ProspectiveShadowLauncherStatus:
    status_id: str
    launcher_ready: bool
    output_exists: bool
    required_paths: tuple[tuple[str, str], ...]
    missing_paths: tuple[str, ...]
    shortcut_name: str
    output_path: str
    config_hash: str
    launcher_version: str = "12G.1.0"
    mode: str = "READ_ONLY_BURN_IN_OPERATOR_LAUNCH"
    scheduler_modified: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    database_write_performed: bool = False
    broker_write_performed: bool = False
    order_api_available: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False
    automatic_promotion_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.status_id
            or not self.shortcut_name.endswith(".lnk")
            or not self.output_path.endswith(".html")
            or not self.config_hash.startswith("sha256:")
            or self.launcher_version != "12G.1.0"
            or self.mode != "READ_ONLY_BURN_IN_OPERATOR_LAUNCH"
            or any(
                (
                    self.scheduler_modified,
                    self.network_used,
                    self.credentials_loaded,
                    self.database_write_performed,
                    self.broker_write_performed,
                    self.order_api_available,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                    self.automatic_promotion_enabled,
                )
            )
            or self.launcher_ready == bool(self.missing_paths)
        ):
            raise ValueError("invalid Phase 12G launcher status")


def load_prospective_shadow_launcher_config(
    path: str | Path,
) -> ProspectiveShadowLauncherConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "launcher_version",
        "mode",
        "python",
        "dashboard_config",
        "render_script",
        "output",
        "shortcut_name",
        "authority",
    }
    authority = {
        "local_process_launch_enabled": True,
        "browser_open_enabled": True,
        "artifact_write_enabled": True,
        "database_read_enabled": True,
        "scheduler_read_enabled": True,
        "scheduler_write_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "database_write_enabled": False,
        "broker_writes_enabled": False,
        "order_api_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }
    if (
        not isinstance(raw, dict)
        or set(raw) != expected
        or raw["launcher_version"] != "12G.1.0"
        or raw["mode"] != "READ_ONLY_BURN_IN_OPERATOR_LAUNCH"
        or raw["authority"] != authority
        or any(
            not _relative(raw.get(name))
            for name in ("python", "dashboard_config", "render_script", "output")
        )
        or not str(raw["python"]).endswith("python.exe")
        or not str(raw["dashboard_config"]).endswith(".json")
        or not str(raw["render_script"]).endswith(".ps1")
        or not str(raw["output"]).endswith(".html")
        or raw["shortcut_name"] != "Trading System.lnk"
    ):
        raise ProspectiveShadowLauncherConfigError(
            "Phase 12G launcher configuration is invalid or unsafe"
        )
    return ProspectiveShadowLauncherConfig(
        str(raw["python"]),
        str(raw["dashboard_config"]),
        str(raw["render_script"]),
        str(raw["output"]),
        str(raw["shortcut_name"]),
        canonical_hash(_freeze(raw)),
    )


def inspect_prospective_shadow_launcher(
    config: ProspectiveShadowLauncherConfig,
    *,
    project_root: str | Path,
) -> ProspectiveShadowLauncherStatus:
    """Inspect one-click launch prerequisites without starting a process."""
    root = Path(project_root).resolve()
    required = (
        ("python", _contained(root, config.python)),
        ("dashboard_config", _contained(root, config.dashboard_config)),
        ("render_script", _contained(root, config.render_script)),
    )
    missing = tuple(name for name, path in required if not path.is_file())
    output = _contained(root, config.output)
    identity = (
        config.config_hash,
        tuple((name, str(path), path.is_file()) for name, path in required),
        str(output),
        output.is_file(),
        config.shortcut_name,
    )
    return ProspectiveShadowLauncherStatus(
        deterministic_id("prospective_shadow_launcher_status", identity),
        not missing,
        output.is_file(),
        tuple((name, str(path)) for name, path in required),
        missing,
        config.shortcut_name,
        str(output),
        config.config_hash,
    )


def _contained(root: Path, value: str) -> Path:
    candidate = (root / value).resolve()
    if candidate != root and root not in candidate.parents:
        raise ProspectiveShadowLauncherConfigError("Phase 12G path escapes project root")
    return candidate


def _relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not Path(value).is_absolute()
        and ".." not in Path(value).parts
        and "\\" not in value
    )


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value
