"""Strict Phase 7D configuration for causal range-reclaim evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class RangeTriggerConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeTriggerConfig:
    values: Mapping[str, object]
    config_hash: str


def load_range_trigger_config(path: str | Path) -> RangeTriggerConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "evidence_version", "trigger", "authority"
    }:
        raise RangeTriggerConfigError("range trigger top-level keys are invalid")
    if raw["evidence_version"] != "7D.1.0":
        raise RangeTriggerConfigError("evidence_version must be 7D.1.0")
    trigger = raw["trigger"]
    authority = raw["authority"]
    expected_trigger = {
        "pattern_family": "RECLAIM",
        "required_state": "ACCEPTED",
        "required_reason_code": "RECLAIM_ACCEPTED",
        "bullish_pattern_name": "BULLISH_RECLAIM",
        "bullish_boundary": "LOWER",
        "bearish_pattern_name": "BEARISH_RECLAIM",
        "bearish_boundary": "UPPER",
        "reference_match": "EXACT",
        "require_event_strictly_after_box": True,
        "retain_all_overlapping_matches": True,
    }
    expected_authority = {
        "research_evidence_only": True,
        "entry_rule_enabled": False,
        "exit_rule_enabled": False,
        "efficacy_claims_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }
    if trigger != expected_trigger:
        raise RangeTriggerConfigError("Phase 7D trigger policy is invalid")
    if authority != expected_authority:
        raise RangeTriggerConfigError("Phase 7D authority must remain evidence-only")
    assert isinstance(trigger, dict) and isinstance(authority, dict)
    frozen = MappingProxyType(
        {
            "evidence_version": raw["evidence_version"],
            "trigger": MappingProxyType(dict(trigger)),
            "authority": MappingProxyType(dict(authority)),
        }
    )
    return RangeTriggerConfig(frozen, canonical_hash(raw))
