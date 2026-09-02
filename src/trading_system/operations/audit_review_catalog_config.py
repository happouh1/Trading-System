"""Strict Phase 6G verified review-bundle catalog configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ObservationAuditReviewCatalogConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationAuditReviewCatalogConfig:
    source_directory: str
    config_hash: str


def load_observation_audit_review_catalog_config(
    path: str | Path,
) -> ObservationAuditReviewCatalogConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "review_catalog_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ObservationAuditReviewCatalogConfigError("review catalog config fields are invalid")
    if raw["review_catalog_version"] != "6G.1.0":
        raise ObservationAuditReviewCatalogConfigError("review_catalog_version must be 6G.1.0")
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
        raise ObservationAuditReviewCatalogConfigError("Phase 6G catalogs have no authority")
    expected_validation = {
        "source_directory": "observation_audit_review_bundles",
        "explicit_bundle_selection_required": True,
        "exact_verified_link_required": True,
        "canonical_source_payloads_required": True,
        "current_code_version_required": True,
        "local_artifact_rehash_required": True,
        "causal_catalog_timestamp_required": True,
        "unique_bundle_ids_required": True,
        "canonical_bundle_order_required": True,
        "append_only": True,
    }
    if raw["validation"] != expected_validation:
        raise ObservationAuditReviewCatalogConfigError("review catalog controls are mandatory")
    directory = str(raw["validation"]["source_directory"])
    pure = PurePosixPath(directory)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ObservationAuditReviewCatalogConfigError("catalog source directory must be contained")
    if raw["thresholds"] != {
        "minimum_bundle_count_defined": False,
        "minimum_reviewer_count_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ObservationAuditReviewCatalogConfigError("Phase 6G cannot invent thresholds")
    return ObservationAuditReviewCatalogConfig(directory, canonical_hash(raw))
