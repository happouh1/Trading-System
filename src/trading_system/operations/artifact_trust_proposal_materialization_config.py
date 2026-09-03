"""Strict Phase 6Y proposal-catalog materialization configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ArtifactTrustProposalMaterializationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalMaterializationConfig:
    config_hash: str


def load_artifact_trust_proposal_materialization_config(
    path: str | Path,
) -> ArtifactTrustProposalMaterializationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_proposal_materialization_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ArtifactTrustProposalMaterializationConfigError(
            "proposal materialization config fields are invalid"
        )
    if raw["artifact_trust_proposal_materialization_version"] != "6Y.1.0":
        raise ArtifactTrustProposalMaterializationConfigError(
            "proposal materialization version must be 6Y.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "caller_membership_override_enabled": False,
        "proposal_selection_enabled": False,
        "policy_activation_enabled": False,
        "signing_enabled": False,
        "reviewer_authentication_enabled": False,
        "consensus_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ArtifactTrustProposalMaterializationConfigError("Phase 6Y has no authority")
    if raw["validation"] != {
        "complete_phase6x_plan_required": True,
        "slot_order_membership_required": True,
        "phase6v_catalog_required": True,
        "strict_timestamp_order_required": True,
        "root_provenance_required": True,
        "single_materialization_per_plan_required": True,
        "exact_source_revalidation_required": True,
        "append_only": True,
    }:
        raise ArtifactTrustProposalMaterializationConfigError(
            "proposal materialization controls are mandatory"
        )
    if raw["thresholds"] != {
        "minimum_slot_count_defined": False,
        "minimum_lead_time_defined": False,
        "completion_threshold_defined": False,
        "quorum_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustProposalMaterializationConfigError(
            "Phase 6Y cannot invent thresholds"
        )
    return ArtifactTrustProposalMaterializationConfig(canonical_hash(raw))
