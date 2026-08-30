"""Strict Phase 5B offline/shadow scheduling and monitoring configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class OperationsMonitorConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationsMonitorConfig:
    minimum_cadence_seconds: int
    maximum_cadence_seconds: int
    overdue_grace_seconds: int
    maximum_jobs: int
    maximum_health_age_seconds: int
    config_hash: str


def _positive(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise OperationsMonitorConfigError(f"{name} must be a positive integer")
    return value


def load_operations_monitor_config(path: str | Path) -> OperationsMonitorConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "monitor_version",
        "authority",
        "scheduler",
        "health",
    }:
        raise OperationsMonitorConfigError("monitor config top-level keys are invalid")
    if raw["monitor_version"] != "5B.1.0":
        raise OperationsMonitorConfigError("monitor_version must be 5B.1.0")
    if raw["authority"] != {
        "offline_shadow_only": True,
        "process_execution_enabled": False,
        "network_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise OperationsMonitorConfigError("Phase 5B authority must remain offline/shadow-only")
    scheduler = raw["scheduler"]
    if not isinstance(scheduler, dict) or set(scheduler) != {
        "minimum_cadence_seconds",
        "maximum_cadence_seconds",
        "overdue_grace_seconds",
        "maximum_jobs",
    }:
        raise OperationsMonitorConfigError("scheduler configuration fields are invalid")
    minimum = _positive(scheduler["minimum_cadence_seconds"], "minimum cadence")
    maximum = _positive(scheduler["maximum_cadence_seconds"], "maximum cadence")
    grace = _positive(scheduler["overdue_grace_seconds"], "overdue grace")
    maximum_jobs = _positive(scheduler["maximum_jobs"], "maximum jobs")
    if minimum > maximum:
        raise OperationsMonitorConfigError("minimum cadence cannot exceed maximum cadence")
    health = raw["health"]
    if not isinstance(health, dict) or set(health) != {
        "maximum_age_seconds",
        "require_all_phase5a_components",
        "future_observation_policy",
    }:
        raise OperationsMonitorConfigError("health configuration fields are invalid")
    if (
        health["require_all_phase5a_components"] is not True
        or health["future_observation_policy"] != "REJECT"
    ):
        raise OperationsMonitorConfigError("Phase 5B health policy is locked")
    maximum_age = _positive(health["maximum_age_seconds"], "maximum health age")
    return OperationsMonitorConfig(
        minimum,
        maximum,
        grace,
        maximum_jobs,
        maximum_age,
        canonical_hash(raw),
    )
