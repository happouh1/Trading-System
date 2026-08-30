"""Strict Phase 5D offline operator-control configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class OperationsControlConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationsControlConfig:
    required_distinct_operators: int
    maximum_approval_lifetime_seconds: int
    default_global_engaged: bool
    component_switches_enabled: bool
    config_hash: str


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise OperationsControlConfigError(f"{name} must be a positive integer")
    return value


def load_operations_control_config(path: str | Path) -> OperationsControlConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "control_version",
        "authority",
        "approvals",
        "kill_switches",
        "cancellation",
    }:
        raise OperationsControlConfigError("control config top-level keys are invalid")
    if raw["control_version"] != "5D.1.0":
        raise OperationsControlConfigError("control_version must be 5D.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "local_operator_evidence_only": True,
        "remote_control_enabled": False,
        "identity_authentication_enabled": False,
        "network_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise OperationsControlConfigError("Phase 5D authority must remain local and offline")
    approvals = raw["approvals"]
    if not isinstance(approvals, dict) or set(approvals) != {
        "required_distinct_operators",
        "maximum_lifetime_seconds",
    }:
        raise OperationsControlConfigError("control approval fields are invalid")
    required = _positive(approvals["required_distinct_operators"], "required operators")
    lifetime = _positive(approvals["maximum_lifetime_seconds"], "approval lifetime")
    if required > 4 or lifetime > 604800:
        raise OperationsControlConfigError("approval controls exceed bounded limits")
    switches = raw["kill_switches"]
    if switches != {
        "default_global_state": "ENGAGED",
        "component_switches_enabled": True,
    }:
        raise OperationsControlConfigError("kill switches must default engaged")
    if raw["cancellation"] != {"pre_execution_only": True}:
        raise OperationsControlConfigError("Phase 5D cancellation must remain pre-execution-only")
    return OperationsControlConfig(required, lifetime, True, True, canonical_hash(raw))
