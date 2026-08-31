"""Strict Phase 6B preregistered-observation-plan configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ObservationPlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationPlanConfig:
    config_hash: str


def load_observation_plan_config(path: str | Path) -> ObservationPlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "observation_plan_version",
        "authority",
        "registration",
        "reconciliation",
        "thresholds",
    }:
        raise ObservationPlanConfigError("observation plan config fields are invalid")
    if raw["observation_plan_version"] != "6B.1.0":
        raise ObservationPlanConfigError("observation_plan_version must be 6B.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ObservationPlanConfigError("Phase 6B must remain offline evidence only")
    if raw["registration"] != {
        "require_registration_before_first_window": True,
        "require_exact_campaign_identity": True,
        "require_exact_campaign_bounds": True,
        "require_exact_window_set": True,
        "require_unique_window_ids": True,
        "require_unique_window_timestamps": True,
        "normalize_window_order": True,
        "immutable_after_registration": True,
    }:
        raise ObservationPlanConfigError("observation plan registration rules are mandatory")
    if raw["reconciliation"] != {
        "verify_plan_payload_hash": True,
        "verify_campaign_payload_hash": True,
        "verify_campaign_window_hashes": True,
        "require_current_code_version": True,
        "retain_incomplete_campaign_status": True,
    }:
        raise ObservationPlanConfigError("observation plan reconciliation rules are mandatory")
    if raw["thresholds"] != {
        "minimum_observation_period_defined": False,
        "minimum_success_rate_defined": False,
        "freshness_service_level_defined": False,
    }:
        raise ObservationPlanConfigError("Phase 6B cannot invent operational thresholds")
    return ObservationPlanConfig(canonical_hash(raw))
