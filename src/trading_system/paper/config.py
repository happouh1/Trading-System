"""Strict Phase 3B operational configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


@dataclass(frozen=True, slots=True)
class PaperConfig:
    values: Mapping[str, object]
    config_hash: str


def load_paper_config(path: str | Path) -> PaperConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "paper_version", "default_mode", "adapter", "heartbeat_interval_seconds",
        "heartbeat_stale_seconds", "completed_bar_lateness_seconds",
        "acknowledgement_timeout_seconds", "unambiguously_unsubmitted_retries",
        "reconciliation_interval_seconds", "maximum_consecutive_data_failures",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 3B configuration keys are invalid")
    if raw["default_mode"] != "SHADOW" or raw["adapter"] != "INTERNAL_SIMULATOR":
        raise ValueError("Phase 3B defaults must be shadow and internal simulator")
    positive = (
        "heartbeat_interval_seconds", "heartbeat_stale_seconds",
        "completed_bar_lateness_seconds", "acknowledgement_timeout_seconds",
        "reconciliation_interval_seconds", "maximum_consecutive_data_failures",
    )
    if any(isinstance(raw[key], bool) or not isinstance(raw[key], int) or raw[key] <= 0
           for key in positive):
        raise ValueError("Phase 3B time and failure thresholds must be positive integers")
    retries = raw["unambiguously_unsubmitted_retries"]
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise ValueError("Phase 3B retry count must be a nonnegative integer")
    if raw["heartbeat_stale_seconds"] <= raw["heartbeat_interval_seconds"]:
        raise ValueError("stale heartbeat threshold must exceed heartbeat interval")
    return PaperConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
