"""Strict Phase 6H preregistered review-catalog plan configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ReviewCatalogPlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewCatalogPlanConfig:
    config_hash: str


def load_review_catalog_plan_config(path: str | Path) -> ReviewCatalogPlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "review_catalog_plan_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ReviewCatalogPlanConfigError("review catalog plan config fields are invalid")
    if raw["review_catalog_plan_version"] != "6H.1.0":
        raise ReviewCatalogPlanConfigError("review_catalog_plan_version must be 6H.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "selection_unbiased_claim_enabled": False,
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
        raise ReviewCatalogPlanConfigError("Phase 6H plans have no authority")
    if raw["validation"] != {
        "exact_catalog_name_required": True,
        "exact_bundle_verification_pairs_required": True,
        "unique_bundle_ids_required": True,
        "canonical_source_order_required": True,
        "registration_before_catalog_required": True,
        "canonical_payload_hashes_required": True,
        "current_code_version_required": True,
        "append_only": True,
        "missing_and_deviation_explicit": True,
    }:
        raise ReviewCatalogPlanConfigError("review catalog plan controls are mandatory")
    if raw["thresholds"] != {
        "minimum_bundle_count_defined": False,
        "minimum_lead_time_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ReviewCatalogPlanConfigError("Phase 6H cannot invent thresholds")
    return ReviewCatalogPlanConfig(canonical_hash(raw))
