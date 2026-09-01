"""Strict Phase 6D offline audit-export configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ObservationAuditExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationAuditExportConfig:
    export_directory: str
    config_hash: str


def load_observation_audit_export_config(path: str | Path) -> ObservationAuditExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "audit_export_version",
        "authority",
        "export",
        "verification",
        "thresholds",
    }:
        raise ObservationAuditExportConfigError(
            "observation audit export config fields are invalid"
        )
    if raw["audit_export_version"] != "6D.1.0":
        raise ObservationAuditExportConfigError("audit_export_version must be 6D.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
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
        raise ObservationAuditExportConfigError("Phase 6D must remain unsigned offline evidence")
    export = raw["export"]
    expected_export = {
        "directory": "observation_audit_exports",
        "canonical_json_required": True,
        "content_addressed_filename_required": True,
        "atomic_write_required": True,
        "conflicting_overwrite_forbidden": True,
        "source_packet_hash_required": True,
        "source_artifact_hashes_required": True,
        "source_artifact_root_required": True,
        "current_code_version_required": True,
        "relative_contained_paths_required": True,
    }
    if export != expected_export:
        raise ObservationAuditExportConfigError("audit export controls are mandatory")
    directory = str(export["directory"])
    pure = PurePosixPath(directory)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise ObservationAuditExportConfigError("audit export directory must be contained")
    if raw["verification"] != {
        "read_only": True,
        "file_hash_required": True,
        "canonical_envelope_required": True,
        "embedded_packet_hash_required": True,
        "embedded_artifact_hashes_required": True,
        "embedded_artifact_root_required": True,
        "source_statuses_retained": True,
    }:
        raise ObservationAuditExportConfigError("audit export verification controls are mandatory")
    if raw["thresholds"] != {
        "minimum_observation_period_defined": False,
        "minimum_success_rate_defined": False,
        "freshness_service_level_defined": False,
        "promotion_threshold_defined": False,
    }:
        raise ObservationAuditExportConfigError("Phase 6D cannot invent operational thresholds")
    return ObservationAuditExportConfig(directory, canonical_hash(raw))
