"""Strict Phase 6F portable review-history configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ObservationAuditReviewExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationAuditReviewExportConfig:
    export_directory: str
    config_hash: str


def load_observation_audit_review_export_config(
    path: str | Path,
) -> ObservationAuditReviewExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "review_export_version",
        "authority",
        "export",
        "verification",
        "thresholds",
    }:
        raise ObservationAuditReviewExportConfigError("review export config fields are invalid")
    if raw["review_export_version"] != "6F.1.0":
        raise ObservationAuditReviewExportConfigError("review_export_version must be 6F.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "reviewer_authentication_enabled": False,
        "consensus_enabled": False,
        "automatic_promotion_enabled": False,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
        "signing_enabled": False,
        "encryption_enabled": False,
    }:
        raise ObservationAuditReviewExportConfigError(
            "Phase 6F must remain unsigned offline evidence"
        )
    expected_export = {
        "directory": "observation_audit_review_bundles",
        "canonical_json_required": True,
        "content_addressed_filename_required": True,
        "atomic_write_required": True,
        "conflicting_overwrite_forbidden": True,
        "complete_review_history_required": True,
        "source_hashes_required": True,
        "current_code_version_required": True,
        "relative_contained_paths_required": True,
    }
    if raw["export"] != expected_export:
        raise ObservationAuditReviewExportConfigError("review export controls are mandatory")
    directory = str(raw["export"]["directory"])
    pure = PurePosixPath(directory)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ObservationAuditReviewExportConfigError("review export directory must be contained")
    if raw["verification"] != {
        "read_only": True,
        "file_hash_required": True,
        "canonical_envelope_required": True,
        "embedded_source_hashes_required": True,
        "embedded_review_hashes_required": True,
        "embedded_review_root_required": True,
        "supersession_history_retained": True,
        "consensus_forbidden": True,
    }:
        raise ObservationAuditReviewExportConfigError(
            "review export verification controls are mandatory"
        )
    if raw["thresholds"] != {
        "minimum_reviewer_count_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
        "promotion_threshold_defined": False,
    }:
        raise ObservationAuditReviewExportConfigError("Phase 6F cannot invent thresholds")
    return ObservationAuditReviewExportConfig(directory, canonical_hash(raw))
