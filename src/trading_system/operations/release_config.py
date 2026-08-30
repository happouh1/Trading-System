"""Strict Phase 5F offline release-evidence configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class OperationsReleaseConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationsReleaseConfig:
    required_statuses: tuple[tuple[str, str], ...]
    config_hash: str


def load_operations_release_config(path: str | Path) -> OperationsReleaseConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "release_evidence_version",
        "authority",
        "required_statuses",
        "consistency",
        "freshness",
    }:
        raise OperationsReleaseConfigError("release evidence config fields are invalid")
    if raw["release_evidence_version"] != "5F.1.0":
        raise OperationsReleaseConfigError("release_evidence_version must be 5F.1.0")
    if raw["authority"] != {
        "offline_only": True,
        "evidence_only": True,
        "production_readiness_claim_enabled": False,
        "network_enabled": False,
        "credentials_enabled": False,
        "external_notifications_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise OperationsReleaseConfigError("Phase 5F must remain offline evidence only")
    statuses = raw["required_statuses"]
    expected = {
        "readiness_manifest": "READY",
        "monitor_report": "READY",
        "control_snapshot": "READY",
        "run_attempt": "SUCCEEDED",
        "restore_verification": "VERIFIED",
    }
    if statuses != expected:
        raise OperationsReleaseConfigError("release evidence statuses are fixed")
    if raw["consistency"] != {
        "control_and_attempt_same_request": True,
        "restore_and_manifest_same_backup": True,
        "require_current_code_version": True,
        "reject_future_evidence": True,
    }:
        raise OperationsReleaseConfigError("release evidence consistency checks are mandatory")
    if raw["freshness"] != {"assessed": False}:
        raise OperationsReleaseConfigError("Phase 5F cannot claim unapproved freshness")
    return OperationsReleaseConfig(tuple(sorted(expected.items())), canonical_hash(raw))
