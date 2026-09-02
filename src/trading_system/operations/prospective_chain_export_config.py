"""Strict Phase 6K prospective-chain export configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from trading_system.serialization import canonical_hash


class ProspectiveChainExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProspectiveChainExportConfig:
    export_directory: str
    config_hash: str


def load_prospective_chain_export_config(path: str | Path) -> ProspectiveChainExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "prospective_chain_export_version",
        "export_directory",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ProspectiveChainExportConfigError(
            "prospective chain export config fields are invalid"
        )
    directory = raw["export_directory"]
    if (
        not isinstance(directory, str)
        or PurePosixPath(directory).is_absolute()
        or len(PurePosixPath(directory).parts) != 1
        or directory in {"", ".", ".."}
    ):
        raise ProspectiveChainExportConfigError(
            "export_directory must be one safe relative segment"
        )
    if raw["prospective_chain_export_version"] != "6K.1.0":
        raise ProspectiveChainExportConfigError("prospective chain export version must be 6K.1.0")
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
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise ProspectiveChainExportConfigError("Phase 6K exports have no authority")
    if raw["validation"] != {
        "exact_source_chain_required": True,
        "canonical_bytes_required": True,
        "content_addressed_path_required": True,
        "contained_path_required": True,
        "atomic_publication_required": True,
        "independent_verification_required": True,
        "canonical_payload_hashes_required": True,
        "current_code_version_required": True,
        "append_only": True,
    }:
        raise ProspectiveChainExportConfigError("prospective chain export controls are mandatory")
    if raw["thresholds"] != {
        "quality_threshold_defined": False,
        "consensus_threshold_defined": False,
        "production_threshold_defined": False,
    }:
        raise ProspectiveChainExportConfigError("Phase 6K cannot invent thresholds")
    return ProspectiveChainExportConfig(directory, canonical_hash(raw))
