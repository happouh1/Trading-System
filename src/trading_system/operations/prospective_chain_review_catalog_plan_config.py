"""Strict Phase 6O preregistered prospective-review catalog plan configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ProspectiveChainReviewCatalogPlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveChainReviewCatalogPlanConfig:
    config_hash: str


def load_prospective_chain_review_catalog_plan_config(
    path: str | Path,
) -> ProspectiveChainReviewCatalogPlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "prospective_review_catalog_plan_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ProspectiveChainReviewCatalogPlanConfigError("catalog plan config fields are invalid")
    if raw["prospective_review_catalog_plan_version"] != "6O.1.0":
        raise ProspectiveChainReviewCatalogPlanConfigError(
            "prospective_review_catalog_plan_version must be 6O.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "selection_unbiased_claim_enabled": False,
        "reviewer_authentication_enabled": False,
        "consensus_enabled": False,
        "ranking_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ProspectiveChainReviewCatalogPlanConfigError("Phase 6O plans have no authority")
    if raw["validation"] != {
        "exact_catalog_name_required": True,
        "exact_bundle_verification_pairs_required": True,
        "unique_bundle_ids_required": True,
        "canonical_source_order_required": True,
        "registration_before_catalog_required": True,
        "exact_phase6n_revalidation_required": True,
        "append_only": True,
        "missing_and_deviation_explicit": True,
    }:
        raise ProspectiveChainReviewCatalogPlanConfigError("catalog plan controls are mandatory")
    if raw["thresholds"] != {
        "minimum_bundle_count_defined": False,
        "minimum_lead_time_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ProspectiveChainReviewCatalogPlanConfigError("Phase 6O cannot invent thresholds")
    return ProspectiveChainReviewCatalogPlanConfig(canonical_hash(raw))
