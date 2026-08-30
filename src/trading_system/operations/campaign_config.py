"""Strict Phase 6A offline shadow-campaign configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class OperationsCampaignConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationsCampaignConfig:
    config_hash: str


def load_operations_campaign_config(path: str | Path) -> OperationsCampaignConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "shadow_campaign_version",
        "authority",
        "validation",
        "freshness",
    }:
        raise OperationsCampaignConfigError("shadow campaign config fields are invalid")
    if raw["shadow_campaign_version"] != "6A.1.0":
        raise OperationsCampaignConfigError("shadow_campaign_version must be 6A.1.0")
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
        raise OperationsCampaignConfigError("Phase 6A must remain offline evidence only")
    if raw["validation"] != {
        "require_complete_release_bundle": True,
        "require_exact_window_timestamp": True,
        "verify_release_payload_hash": True,
        "verify_source_evidence_hashes": True,
        "require_current_code_version": True,
        "reject_future_evidence": True,
        "normalize_window_order": True,
    }:
        raise OperationsCampaignConfigError("shadow campaign validation rules are mandatory")
    if raw["freshness"] != {
        "service_level_assessed": False,
        "minimum_observation_period_defined": False,
        "minimum_success_rate_defined": False,
    }:
        raise OperationsCampaignConfigError("Phase 6A cannot invent operational thresholds")
    return OperationsCampaignConfig(canonical_hash(raw))
