"""Strict Phase 3D operational configuration and capability manifest."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


@dataclass(frozen=True, slots=True)
class WebullExitConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class WebullExitCapabilities:
    values: Mapping[str, object]
    capability_hash: str
    approved: bool


def load_exit_config(path: str | Path) -> WebullExitConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "phase_3d_version",
        "environment",
        "protective_stop",
        "queued_exit",
        "recovery",
        "exit_environment_flag",
        "flatten_environment_flag",
        "live_smoke_required_adjustment_factor",
        "authorization_max_age_seconds",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 3D configuration keys are invalid")
    if raw["phase_3d_version"] != "3D.1.0" or raw["environment"] != "SANDBOX":
        raise ValueError("unsupported Phase 3D version or environment")
    if raw["protective_stop"] != {
        "order_type": "STOP_LOSS",
        "time_in_force": "GTC",
        "extended_hours": False,
        "replace_only_when_monotonic": True,
    }:
        raise ValueError("unsupported Phase 3D protective-stop policy")
    if raw["queued_exit"] != {
        "order_type": "MARKET",
        "time_in_force": "DAY",
        "cancel_stop_first": True,
    }:
        raise ValueError("unsupported Phase 3D queued-exit policy")
    if raw["recovery"] != {
        "same_client_query_count": 1,
        "automatic_write_retry_count": 0,
        "max_inflight_actions_per_position": 1,
    }:
        raise ValueError("unsupported Phase 3D recovery policy")
    if raw["exit_environment_flag"] != "WEBULL_SANDBOX_EXIT_ENABLED":
        raise ValueError("Phase 3D exit environment flag is fixed")
    if raw["flatten_environment_flag"] != "WEBULL_SANDBOX_FLATTEN_ENABLED":
        raise ValueError("Phase 3D flatten environment flag is fixed")
    if raw["live_smoke_required_adjustment_factor"] != 1:
        raise ValueError("Phase 3D live smoke tests require factor-one evidence")
    age = raw["authorization_max_age_seconds"]
    if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
        raise ValueError("Phase 3D authorization age must be a positive integer")
    return WebullExitConfig(MappingProxyType(dict(raw)), canonical_hash(raw))


def load_exit_capabilities(path: str | Path) -> WebullExitCapabilities:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "manifest_version",
        "environment",
        "sdk_version",
        "approved",
        "validated_capabilities",
        "official_exit_transport_enabled",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 3D capability manifest keys are invalid")
    if (
        raw["manifest_version"] != "3D-CAP.1.0"
        or raw["environment"] != "SANDBOX"
        or raw["sdk_version"] != "2.0.17"
    ):
        raise ValueError("unsupported Phase 3D capability manifest")
    capabilities = raw["validated_capabilities"]
    if not isinstance(capabilities, list) or not all(
        isinstance(value, str) for value in capabilities
    ):
        raise ValueError("Phase 3D validated capabilities must be a string list")
    approved = raw["approved"]
    official = raw["official_exit_transport_enabled"]
    if not isinstance(approved, bool) or not isinstance(official, bool):
        raise ValueError("Phase 3D capability gates must be booleans")
    required = {
        "LONG_STOP_PLACE_DETAIL_CANCEL",
        "LONG_STOP_SAME_ID_REPLACE",
        "LONG_MARKET_REDUCING_EXIT",
        "SHORT_BUY_COVER_NETTING",
        "PARTIAL_FILL_CUMULATIVE_BEHAVIOR",
        "AMBIGUITY_SAME_ID_RECOVERY",
        "RESTART_EXISTING_PROTECTION",
    }
    if approved and (set(capabilities) != required or not official):
        raise ValueError("approved Phase 3D manifest lacks exact required capabilities")
    if official and not approved:
        raise ValueError("official Phase 3D transport cannot precede approval")
    return WebullExitCapabilities(
        MappingProxyType(dict(raw)), canonical_hash(raw), approved
    )
