"""Strict Phase 6X prospective artifact-trust proposal-plan configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ArtifactTrustProposalPlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalPlanConfig:
    config_hash: str


def load_artifact_trust_proposal_plan_config(
    path: str | Path,
) -> ArtifactTrustProposalPlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_proposal_plan_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ArtifactTrustProposalPlanConfigError("proposal plan config fields are invalid")
    if raw["artifact_trust_proposal_plan_version"] != "6X.1.0":
        raise ArtifactTrustProposalPlanConfigError("proposal plan version must be 6X.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "proposal_content_enabled": False,
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
        raise ArtifactTrustProposalPlanConfigError("Phase 6X plans have no authority")
    if raw["validation"] != {
        "registration_before_all_windows_required": True,
        "unique_slot_ids_required": True,
        "unique_windows_required": True,
        "canonical_slot_order_required": True,
        "single_binding_per_slot_required": True,
        "single_slot_per_proposal_required": True,
        "proposal_within_window_required": True,
        "exact_phase6t_evidence_required": True,
        "exact_phase6u_revalidation_required": True,
        "canonical_payload_hashes_required": True,
        "current_code_version_required": True,
        "append_only": True,
    }:
        raise ArtifactTrustProposalPlanConfigError("proposal plan controls are mandatory")
    if raw["thresholds"] != {
        "minimum_slot_count_defined": False,
        "minimum_lead_time_defined": False,
        "window_duration_threshold_defined": False,
        "completion_threshold_defined": False,
        "quorum_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustProposalPlanConfigError("Phase 6X cannot invent thresholds")
    return ArtifactTrustProposalPlanConfig(canonical_hash(raw))
