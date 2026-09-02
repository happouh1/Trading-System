"""Strict Phase 6U unauthenticated policy-proposal configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ArtifactTrustPolicyProposalConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustPolicyProposalConfig:
    config_hash: str


def load_artifact_trust_policy_proposal_config(
    path: str | Path,
) -> ArtifactTrustPolicyProposalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_policy_proposal_version",
        "authority",
        "proposal",
        "thresholds",
    }:
        raise ArtifactTrustPolicyProposalConfigError("policy proposal fields are invalid")
    if raw["artifact_trust_policy_proposal_version"] != "6U.1.0":
        raise ArtifactTrustPolicyProposalConfigError(
            "artifact_trust_policy_proposal_version must be 6U.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "proposal_only": True,
        "policy_activation_enabled": False,
        "signing_enabled": False,
        "encryption_enabled": False,
        "key_access_enabled": False,
        "trusted_timestamp_enabled": False,
        "external_transport_enabled": False,
        "reviewer_authentication_enabled": False,
        "consensus_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ArtifactTrustPolicyProposalConfigError("Phase 6U has no approval authority")
    if raw["proposal"] != {
        "exact_verified_phase6t_export_required": True,
        "all_six_policy_answers_required": True,
        "unresolved_answer_forbidden": True,
        "secret_and_key_material_forbidden": True,
        "causal_proposal_time_required": True,
        "canonical_payload_required": True,
        "append_only": True,
        "status": "PROPOSED_UNAUTHENTICATED",
    }:
        raise ArtifactTrustPolicyProposalConfigError("policy proposal controls are mandatory")
    if raw["thresholds"] != {
        "reviewer_count_defined": False,
        "approval_threshold_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustPolicyProposalConfigError("Phase 6U cannot invent thresholds")
    return ArtifactTrustPolicyProposalConfig(canonical_hash(raw))
