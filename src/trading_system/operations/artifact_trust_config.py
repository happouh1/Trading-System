"""Strict Phase 6S unresolved artifact-trust foundation configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ArtifactTrustConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustConfig:
    signature_algorithm: str
    key_custody: str
    signer_identity: str
    trusted_timestamp_provider: str
    revocation_policy: str
    receiving_verifier: str
    config_hash: str


def load_artifact_trust_config(path: str | Path) -> ArtifactTrustConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_foundation_version",
        "authority",
        "policy",
        "validation",
        "thresholds",
    }:
        raise ArtifactTrustConfigError("artifact trust config fields are invalid")
    if raw["artifact_trust_foundation_version"] != "6S.1.0":
        raise ArtifactTrustConfigError("artifact_trust_foundation_version must be 6S.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "signing_enabled": False,
        "key_generation_enabled": False,
        "key_loading_enabled": False,
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
        raise ArtifactTrustConfigError("Phase 6S has no signing or operational authority")
    unresolved = {
        "signature_algorithm": "UNRESOLVED",
        "key_custody": "UNRESOLVED",
        "signer_identity": "UNRESOLVED",
        "trusted_timestamp_provider": "UNRESOLVED",
        "revocation_policy": "UNRESOLVED",
        "receiving_verifier": "UNRESOLVED",
    }
    if raw["policy"] != unresolved:
        raise ArtifactTrustConfigError("Phase 6S trust choices must remain unresolved")
    if raw["validation"] != {
        "exact_verified_phase6r_export_required": True,
        "canonical_source_hashes_required": True,
        "causal_request_time_required": True,
        "explicit_blockers_required": True,
        "unsigned_state_required": True,
        "single_request_per_policy_export_verification_required": True,
        "append_only": True,
    }:
        raise ArtifactTrustConfigError("artifact trust controls are mandatory")
    if raw["thresholds"] != {
        "minimum_signer_count_defined": False,
        "signature_quorum_defined": False,
        "timestamp_age_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustConfigError("Phase 6S cannot invent trust thresholds")
    policy = raw["policy"]
    return ArtifactTrustConfig(
        str(policy["signature_algorithm"]),
        str(policy["key_custody"]),
        str(policy["signer_identity"]),
        str(policy["trusted_timestamp_provider"]),
        str(policy["revocation_policy"]),
        str(policy["receiving_verifier"]),
        canonical_hash(raw),
    )
