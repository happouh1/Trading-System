"""Strict Phase 6R portable materialization-chain export configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ProspectiveReviewBundleChainExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundleChainExportConfig:
    export_directory: str
    config_hash: str


def load_prospective_review_bundle_chain_export_config(
    path: str | Path,
) -> ProspectiveReviewBundleChainExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "review_bundle_chain_export_version",
        "authority",
        "export",
        "verification",
        "thresholds",
    }:
        raise ProspectiveReviewBundleChainExportConfigError("chain export fields are invalid")
    if raw["review_bundle_chain_export_version"] != "6R.1.0":
        raise ProspectiveReviewBundleChainExportConfigError(
            "review_bundle_chain_export_version must be 6R.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "signing_enabled": False,
        "encryption_enabled": False,
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
        raise ProspectiveReviewBundleChainExportConfigError("Phase 6R has no authority")
    expected_export = {
        "directory": "prospective_review_bundle_materialization_chains",
        "canonical_json_required": True,
        "content_addressed_filename_required": True,
        "atomic_write_required": True,
        "conflicting_overwrite_forbidden": True,
        "complete_phase6p_6o_6n_6q_chain_required": True,
        "source_hashes_required": True,
        "chain_root_required": True,
        "current_code_version_required": True,
        "relative_contained_paths_required": True,
    }
    if raw["export"] != expected_export:
        raise ProspectiveReviewBundleChainExportConfigError("chain export controls are mandatory")
    directory = str(raw["export"]["directory"])
    pure = PurePosixPath(directory)
    if pure.is_absolute() or len(pure.parts) != 1 or directory in {"", ".", ".."}:
        raise ProspectiveReviewBundleChainExportConfigError(
            "chain export directory must be one safe relative segment"
        )
    if raw["verification"] != {
        "read_only": True,
        "file_hash_required": True,
        "canonical_envelope_required": True,
        "embedded_source_hashes_required": True,
        "embedded_chain_root_required": True,
        "manifest_binding_required": True,
    }:
        raise ProspectiveReviewBundleChainExportConfigError(
            "chain verification controls are mandatory"
        )
    if raw["thresholds"] != {
        "quality_threshold_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
        "promotion_threshold_defined": False,
    }:
        raise ProspectiveReviewBundleChainExportConfigError("Phase 6R cannot invent thresholds")
    return ProspectiveReviewBundleChainExportConfig(directory, canonical_hash(raw))
