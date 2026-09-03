"""Strict Phase 6W artifact-trust proposal-catalog plan configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ArtifactTrustProposalCatalogPlanConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalCatalogPlanConfig:
    config_hash: str


def load_artifact_trust_proposal_catalog_plan_config(
    path: str | Path,
) -> ArtifactTrustProposalCatalogPlanConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_proposal_catalog_plan_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ArtifactTrustProposalCatalogPlanConfigError(
            "proposal catalog plan fields are invalid"
        )
    if raw["artifact_trust_proposal_catalog_plan_version"] != "6W.1.0":
        raise ArtifactTrustProposalCatalogPlanConfigError("plan version must be 6W.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
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
        raise ArtifactTrustProposalCatalogPlanConfigError("Phase 6W plans have no authority")
    if raw["validation"] != {
        "exact_phase6u_proposal_ids_required": True,
        "exact_proposal_payload_hashes_required": True,
        "canonical_sorted_unique_sources_required": True,
        "registration_before_catalog_required": True,
        "exact_phase6v_revalidation_required": True,
        "append_only": True,
        "missing_and_deviation_explicit": True,
    }:
        raise ArtifactTrustProposalCatalogPlanConfigError("plan controls are mandatory")
    if raw["thresholds"] != {
        "minimum_proposal_count_defined": False,
        "minimum_lead_time_defined": False,
        "quorum_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustProposalCatalogPlanConfigError("Phase 6W cannot invent thresholds")
    return ArtifactTrustProposalCatalogPlanConfig(canonical_hash(raw))
