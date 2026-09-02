"""Strict Phase 6Q deterministic materialization configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ProspectiveReviewBundleMaterializationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundleMaterializationConfig:
    config_hash: str


def load_prospective_review_bundle_materialization_config(
    path: str | Path,
) -> ProspectiveReviewBundleMaterializationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "review_bundle_materialization_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ProspectiveReviewBundleMaterializationConfigError(
            "materialization fields are invalid"
        )
    if raw["review_bundle_materialization_version"] != "6Q.1.0":
        raise ProspectiveReviewBundleMaterializationConfigError(
            "review_bundle_materialization_version must be 6Q.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "caller_membership_override_enabled": False,
        "consensus_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ProspectiveReviewBundleMaterializationConfigError("Phase 6Q has no authority")
    if raw["validation"] != {
        "complete_phase6p_plan_required": True,
        "slot_order_membership_required": True,
        "phase6o_plan_required": True,
        "phase6n_catalog_required": True,
        "strict_timestamp_order_required": True,
        "root_provenance_required": True,
        "single_materialization_per_plan_required": True,
        "append_only": True,
    }:
        raise ProspectiveReviewBundleMaterializationConfigError(
            "materialization controls are mandatory"
        )
    if raw["thresholds"] != {
        "minimum_slot_count_defined": False,
        "minimum_lead_time_defined": False,
        "production_threshold_defined": False,
    }:
        raise ProspectiveReviewBundleMaterializationConfigError("Phase 6Q cannot invent thresholds")
    return ProspectiveReviewBundleMaterializationConfig(canonical_hash(raw))
