"""Strict Phase 6V descriptive proposal-catalog configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ArtifactTrustProposalCatalogConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalCatalogConfig:
    config_hash: str


def load_artifact_trust_proposal_catalog_config(
    path: str | Path,
) -> ArtifactTrustProposalCatalogConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_proposal_catalog_version",
        "authority",
        "catalog",
        "thresholds",
    }:
        raise ArtifactTrustProposalCatalogConfigError("proposal catalog fields are invalid")
    if raw["artifact_trust_proposal_catalog_version"] != "6V.1.0":
        raise ArtifactTrustProposalCatalogConfigError("catalog version must be 6V.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "catalog_only": True,
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
        raise ArtifactTrustProposalCatalogConfigError("Phase 6V has no selection authority")
    if raw["catalog"] != {
        "exact_phase6u_proposals_required": True,
        "same_verified_phase6t_source_required": True,
        "canonical_sorted_unique_proposal_ids_required": True,
        "field_by_field_descriptive_comparison": True,
        "causal_catalog_time_required": True,
        "canonical_payload_required": True,
        "append_only": True,
    }:
        raise ArtifactTrustProposalCatalogConfigError("catalog controls are mandatory")
    if raw["thresholds"] != {
        "minimum_proposal_count_defined": False,
        "quorum_defined": False,
        "approval_threshold_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustProposalCatalogConfigError("Phase 6V cannot invent thresholds")
    return ArtifactTrustProposalCatalogConfig(canonical_hash(raw))
