"""Strict Phase 6C offline observation-audit configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ObservationAuditConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationAuditConfig:
    config_hash: str


def load_observation_audit_config(path: str | Path) -> ObservationAuditConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "audit_packet_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ObservationAuditConfigError("observation audit config fields are invalid")
    if raw["audit_packet_version"] != "6C.1.0":
        raise ObservationAuditConfigError("audit_packet_version must be 6C.1.0")
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
        raise ObservationAuditConfigError("Phase 6C must remain offline evidence only")
    if raw["validation"] != {
        "verify_plan_payload_hash": True,
        "verify_reconciliation_payload_hash": True,
        "verify_campaign_payload_hash": True,
        "verify_all_child_payload_hashes": True,
        "verify_cross_record_links": True,
        "require_current_code_version": True,
        "require_causal_packet_timestamp": True,
        "normalize_artifact_order": True,
        "retain_source_statuses": True,
    }:
        raise ObservationAuditConfigError("observation audit validation rules are mandatory")
    if raw["thresholds"] != {
        "minimum_observation_period_defined": False,
        "minimum_success_rate_defined": False,
        "freshness_service_level_defined": False,
        "promotion_threshold_defined": False,
    }:
        raise ObservationAuditConfigError("Phase 6C cannot invent operational thresholds")
    return ObservationAuditConfig(canonical_hash(raw))
