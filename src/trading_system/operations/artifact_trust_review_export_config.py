"""Strict Phase 6T local artifact-trust review export configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ArtifactTrustReviewExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactTrustReviewExportConfig:
    export_directory: str
    config_hash: str


def load_artifact_trust_review_export_config(
    path: str | Path,
) -> ArtifactTrustReviewExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "artifact_trust_review_export_version",
        "authority",
        "export",
        "verification",
        "thresholds",
    }:
        raise ArtifactTrustReviewExportConfigError(
            "artifact trust review export fields are invalid"
        )
    if raw["artifact_trust_review_export_version"] != "6T.1.0":
        raise ArtifactTrustReviewExportConfigError(
            "artifact_trust_review_export_version must be 6T.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
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
        raise ArtifactTrustReviewExportConfigError("Phase 6T has no authority")
    expected_export = {
        "directory": "artifact_trust_review_packets",
        "canonical_json_required": True,
        "content_addressed_filename_required": True,
        "atomic_write_required": True,
        "conflicting_overwrite_forbidden": True,
        "exact_phase6r_6s_lineage_required": True,
        "source_hashes_required": True,
        "chain_root_required": True,
        "current_code_version_required": True,
        "relative_contained_paths_required": True,
    }
    if raw["export"] != expected_export:
        raise ArtifactTrustReviewExportConfigError("review export controls are mandatory")
    directory = str(raw["export"]["directory"])
    pure = PurePosixPath(directory)
    if pure.is_absolute() or len(pure.parts) != 1 or directory in {"", ".", ".."}:
        raise ArtifactTrustReviewExportConfigError(
            "review export directory must be one safe relative segment"
        )
    if raw["verification"] != {
        "read_only": True,
        "file_hash_required": True,
        "canonical_envelope_required": True,
        "embedded_source_hashes_required": True,
        "embedded_chain_root_required": True,
        "manifest_binding_required": True,
    }:
        raise ArtifactTrustReviewExportConfigError("review verification controls are mandatory")
    if raw["thresholds"] != {
        "reviewer_count_defined": False,
        "approval_threshold_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ArtifactTrustReviewExportConfigError("Phase 6T cannot invent thresholds")
    return ArtifactTrustReviewExportConfig(directory, canonical_hash(raw))
