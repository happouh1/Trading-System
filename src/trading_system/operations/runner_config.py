"""Strict Phase 5C packaged-worker runner configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash

_ACTIONS = {"EVIDENCE_NOOP", "SQLITE_QUICK_CHECK"}


class OperationsRunnerConfigError(ValueError):
    pass


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise OperationsRunnerConfigError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class OperationsRunnerConfig:
    allowed_actions: tuple[str, ...]
    timeout_seconds: int
    lease_grace_seconds: int
    maximum_attempts: int
    retry_backoff_seconds: int
    maximum_output_bytes: int
    workspace_root: Path
    config_hash: str


def load_operations_runner_config(path: str | Path) -> OperationsRunnerConfig:
    config_path = Path(path).resolve()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"runner_version", "authority", "worker"}:
        raise OperationsRunnerConfigError("runner config top-level keys are invalid")
    if raw["runner_version"] != "5C.1.0":
        raise OperationsRunnerConfigError("runner_version must be 5C.1.0")
    if raw["authority"] != {
        "offline_shadow_only": True,
        "packaged_workers_only": True,
        "shell_enabled": False,
        "arbitrary_executables_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise OperationsRunnerConfigError("Phase 5C authority must remain packaged and offline")
    worker = raw["worker"]
    if not isinstance(worker, dict) or set(worker) != {
        "allowed_actions",
        "timeout_seconds",
        "lease_grace_seconds",
        "maximum_attempts",
        "retry_backoff_seconds",
        "maximum_output_bytes",
        "workspace_root",
    }:
        raise OperationsRunnerConfigError("runner worker fields are invalid")
    actions = worker["allowed_actions"]
    if (
        not isinstance(actions, list)
        or not actions
        or not all(isinstance(item, str) and item in _ACTIONS for item in actions)
        or len(set(actions)) != len(actions)
    ):
        raise OperationsRunnerConfigError("runner actions must be unique packaged actions")
    root_value = worker["workspace_root"]
    if not isinstance(root_value, str) or not root_value:
        raise OperationsRunnerConfigError("runner workspace root is required")
    root = (config_path.parent / root_value).resolve()
    if not root.is_dir():
        raise OperationsRunnerConfigError("runner workspace root must exist")
    timeout = _positive(worker["timeout_seconds"], "worker timeout")
    grace = _positive(worker["lease_grace_seconds"], "lease grace")
    attempts = _positive(worker["maximum_attempts"], "maximum attempts")
    backoff = _positive(worker["retry_backoff_seconds"], "retry backoff")
    output = _positive(worker["maximum_output_bytes"], "maximum output bytes")
    if timeout > 3600 or grace > 3600:
        raise OperationsRunnerConfigError("runner timeout and lease grace cannot exceed one hour")
    if attempts > 5:
        raise OperationsRunnerConfigError("runner attempts cannot exceed five")
    if backoff > 86400:
        raise OperationsRunnerConfigError("runner retry backoff cannot exceed one day")
    if output > 1048576:
        raise OperationsRunnerConfigError("runner output limit cannot exceed one MiB")
    return OperationsRunnerConfig(
        tuple(sorted(actions)),
        timeout,
        grace,
        attempts,
        backoff,
        output,
        root,
        canonical_hash(raw),
    )
