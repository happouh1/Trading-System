"""Strict Phase 6P prospective review-bundle slot configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ProspectiveReviewBundlePlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundlePlanConfig:
    config_hash: str


def load_prospective_review_bundle_plan_config(
    path: str | Path,
) -> ProspectiveReviewBundlePlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "prospective_review_bundle_plan_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ProspectiveReviewBundlePlanConfigError("review-bundle plan fields are invalid")
    if raw["prospective_review_bundle_plan_version"] != "6P.1.0":
        raise ProspectiveReviewBundlePlanConfigError(
            "prospective_review_bundle_plan_version must be 6P.1.0"
        )
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
        raise ProspectiveReviewBundlePlanConfigError("Phase 6P plans have no authority")
    if raw["validation"] != {
        "registration_before_all_slots_required": True,
        "unique_slot_ids_required": True,
        "unique_expected_times_required": True,
        "canonical_slot_order_required": True,
        "single_binding_per_slot_required": True,
        "single_bundle_per_plan_required": True,
        "verified_phase6m_bundle_required": True,
        "bundle_verification_after_registration_required": True,
        "full_phase6n_source_validation_required": True,
        "append_only": True,
    }:
        raise ProspectiveReviewBundlePlanConfigError("review-bundle plan controls are mandatory")
    if raw["thresholds"] != {
        "minimum_slot_count_defined": False,
        "minimum_lead_time_defined": False,
        "timing_tolerance_defined": False,
        "completion_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ProspectiveReviewBundlePlanConfigError("Phase 6P cannot invent thresholds")
    return ProspectiveReviewBundlePlanConfig(canonical_hash(raw))
