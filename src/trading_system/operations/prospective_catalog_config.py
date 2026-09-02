"""Strict Phase 6J prospective catalog materialization configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ProspectiveCatalogMaterializationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveCatalogMaterializationConfig:
    config_hash: str


def load_prospective_catalog_materialization_config(
    path: str | Path,
) -> ProspectiveCatalogMaterializationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "prospective_catalog_materialization_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ProspectiveCatalogMaterializationConfigError(
            "materialization config fields are invalid"
        )
    if raw["prospective_catalog_materialization_version"] != "6J.1.0":
        raise ProspectiveCatalogMaterializationConfigError("materialization version must be 6J.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "caller_membership_override_enabled": False,
        "reviewer_authentication_enabled": False,
        "consensus_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ProspectiveCatalogMaterializationConfigError("Phase 6J has no authority")
    if raw["validation"] != {
        "complete_plan_required": True,
        "exact_slot_bindings_required": True,
        "catalog_name_from_plan_required": True,
        "catalog_membership_from_bindings_required": True,
        "canonical_payload_hashes_required": True,
        "current_code_version_required": True,
        "single_catalog_per_plan_required": True,
        "append_only": True,
    }:
        raise ProspectiveCatalogMaterializationConfigError("materialization controls are mandatory")
    if raw["thresholds"] != {
        "minimum_slot_count_defined": False,
        "review_quality_threshold_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ProspectiveCatalogMaterializationConfigError("Phase 6J cannot invent thresholds")
    return ProspectiveCatalogMaterializationConfig(canonical_hash(raw))
