"""Deterministic Phase 9G desktop-launch readiness inspection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class DesktopLaunchConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DesktopLaunchConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class DesktopLaunchStatus:
    status_id: str
    project_root: str
    mode: str
    required_paths: tuple[tuple[str, str], ...]
    missing_paths: tuple[str, ...]
    operator_home_ready: bool
    config_hash: str
    launcher_version: str = "9G.1.0"
    scheduler_started: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.status_id
            or not self.project_root
            or self.mode != "READ_ONLY_OPERATOR_HOME"
            or not self.required_paths
            or self.required_paths != tuple(sorted(self.required_paths))
            or self.missing_paths != tuple(sorted(set(self.missing_paths)))
            or self.operator_home_ready != (not self.missing_paths)
            or not self.config_hash.startswith("sha256:")
            or self.launcher_version != "9G.1.0"
            or self.scheduler_started
            or self.network_used
            or self.credentials_loaded
            or self.broker_write_performed
            or self.sandbox_execution_enabled
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9G desktop launch status")


def load_desktop_launch_config(path: str | Path) -> DesktopLaunchConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "launcher_version", "mode", "display", "paths", "authority"
    }:
        raise DesktopLaunchConfigError("Phase 9G configuration keys are invalid")
    if raw["launcher_version"] != "9G.1.0" or raw["mode"] != "READ_ONLY_OPERATOR_HOME":
        raise DesktopLaunchConfigError("Phase 9G mode is invalid")
    if raw["display"] != {
        "title": "Trading System",
        "shortcut_name": "Trading System.lnk",
    }:
        raise DesktopLaunchConfigError("Phase 9G display settings are invalid")
    paths = raw["paths"]
    if not isinstance(paths, dict) or set(paths) != {
        "python", "thresholds", "paper_config", "webull_config"
    } or any(not _canonical_relative_path(value) for value in paths.values()):
        raise DesktopLaunchConfigError("Phase 9G paths are invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or any(value is not False for value in authority.values()):
        raise DesktopLaunchConfigError("Phase 9G authority must remain disabled")
    if set(authority) != {
        "process_scheduler_enabled", "network_enabled", "credential_loading_enabled",
        "broker_writes_enabled", "sandbox_execution_enabled", "live_trading_enabled",
    }:
        raise DesktopLaunchConfigError("Phase 9G authority keys are invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return DesktopLaunchConfig(MappingProxyType(frozen), canonical_hash(raw))


def inspect_desktop_launcher(
    config: DesktopLaunchConfig,
    *,
    project_root: str | Path,
) -> DesktopLaunchStatus:
    root = Path(project_root).resolve()
    paths = config.values["paths"]
    if not isinstance(paths, Mapping):
        raise TypeError("validated Phase 9G paths must be a mapping")
    required = tuple(sorted((str(name), str(value)) for name, value in paths.items()))
    missing = tuple(sorted(name for name, relative in required if not (root / relative).is_file()))
    identity = (str(root), "READ_ONLY_OPERATOR_HOME", required, missing, config.config_hash)
    return DesktopLaunchStatus(
        deterministic_id("desktop_launch_status", identity), str(root),
        "READ_ONLY_OPERATOR_HOME", required, missing, not missing, config.config_hash,
    )


def _canonical_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts
