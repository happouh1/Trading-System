"""Strict Phase 6E offline audit-review configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.serialization import canonical_hash


class ObservationAuditReviewConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationAuditReviewConfig:
    config_hash: str


def load_observation_audit_review_config(path: str | Path) -> ObservationAuditReviewConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "audit_review_version",
        "authority",
        "validation",
        "thresholds",
    }:
        raise ObservationAuditReviewConfigError(
            "observation audit review config fields are invalid"
        )
    if raw["audit_review_version"] != "6E.1.0":
        raise ObservationAuditReviewConfigError("audit_review_version must be 6E.1.0")
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
    }:
        raise ObservationAuditReviewConfigError("Phase 6E reviews have no authority")
    if raw["validation"] != {
        "require_verified_export": True,
        "require_exact_verification_link": True,
        "verify_manifest_payload_hash": True,
        "verify_verification_payload_hash": True,
        "require_current_code_version": True,
        "require_causal_review_timestamp": True,
        "canonical_reason_order": True,
        "append_only": True,
        "retain_all_prior_reviews": True,
        "supersession_same_export_reviewer": True,
        "reviewer_identity_is_asserted": True,
        "uncertain_excluded_from_summary": True,
    }:
        raise ObservationAuditReviewConfigError("audit review validation rules are mandatory")
    if raw["thresholds"] != {
        "minimum_reviewer_count_defined": False,
        "consensus_threshold_defined": False,
        "minimum_observation_period_defined": False,
        "production_threshold_defined": False,
    }:
        raise ObservationAuditReviewConfigError("Phase 6E cannot invent review thresholds")
    return ObservationAuditReviewConfig(canonical_hash(raw))
