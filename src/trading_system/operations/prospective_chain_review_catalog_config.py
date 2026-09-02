"""Strict Phase 6N verified prospective-review bundle catalog configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ProspectiveChainReviewCatalogConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveChainReviewCatalogConfig:
    source_directory: str
    config_hash: str


def load_prospective_chain_review_catalog_config(
    path: str | Path,
) -> ProspectiveChainReviewCatalogConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "prospective_review_catalog_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ProspectiveChainReviewCatalogConfigError("review catalog config fields are invalid")
    if raw["prospective_review_catalog_version"] != "6N.1.0":
        raise ProspectiveChainReviewCatalogConfigError(
            "prospective_review_catalog_version must be 6N.1.0"
        )
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "reviewer_authentication_enabled": False,
        "consensus_enabled": False,
        "ranking_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ProspectiveChainReviewCatalogConfigError("Phase 6N catalogs have no authority")
    if raw["validation"] != {
        "source_directory": "prospective_chain_review_bundles",
        "explicit_bundle_selection_required": True,
        "exact_verified_link_required": True,
        "canonical_source_payloads_required": True,
        "chain_and_review_roots_required": True,
        "current_code_version_required": True,
        "local_artifact_rehash_required": True,
        "causal_catalog_timestamp_required": True,
        "unique_bundle_ids_required": True,
        "canonical_bundle_order_required": True,
        "append_only": True,
    }:
        raise ProspectiveChainReviewCatalogConfigError("review catalog controls are mandatory")
    directory = str(raw["validation"]["source_directory"])
    pure = PurePosixPath(directory)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ProspectiveChainReviewCatalogConfigError("catalog source directory must be contained")
    if raw["thresholds"] != {
        "minimum_bundle_count_defined": False,
        "minimum_reviewer_count_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ProspectiveChainReviewCatalogConfigError("Phase 6N cannot invent thresholds")
    return ProspectiveChainReviewCatalogConfig(directory, canonical_hash(raw))
