"""Append-only Phase 7N verification receipts for local Phase 7M exports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.range_evidence_bundle import RangeEvidenceBundleConfig
from trading_system.reporting.reviewed_range_bundle import (
    ReviewedRangeBundleConfig,
    ReviewedRangeBundleRegistry,
    verify_reviewed_range_bundle,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "CALLER_ASSERTED_TIME_IS_NOT_A_TRUSTED_TIMESTAMP",
    "LOCAL_VERIFICATION_IS_NOT_A_SIGNATURE_OR_APPROVAL",
    "NO_CONSENSUS_EFFICACY_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeBundleAuditConfigError(ValueError):
    pass


class ReviewedRangeBundleAuditStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReviewedRangeBundleAuditConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeBundleAuditReceipt:
    verification_id: str
    reviewed_bundle_export_id: str
    reviewed_bundle_id: str
    verified_at: datetime
    status: ReviewedRangeBundleAuditStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    config_hash: str
    source_config_hash: str
    verification_version: str = "7N.1.0"
    trusted_timestamp: bool = False
    signed: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES


def load_reviewed_range_bundle_audit_config(
    path: str | Path,
) -> ReviewedRangeBundleAuditConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "verification_version", "source", "verification", "failure_policy", "timestamp",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeBundleAuditConfigError("Phase 7N configuration keys are invalid")
    if (
        raw["verification_version"] != "7N.1.0"
        or raw["source"] != "PERSISTED_PHASE7M_LOCAL_EXPORT"
        or raw["verification"] != "REHASH_AND_FULL_OFFLINE_NESTED_VERIFY"
        or raw["failure_policy"] != "APPEND_RECEIPT_AND_FAIL_CLOSED"
        or raw["timestamp"] != "CALLER_ASSERTED_UNTRUSTED_AWARE"
    ):
        raise ReviewedRangeBundleAuditConfigError("Phase 7N verification policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "network_enabled", "signature_enabled", "trusted_timestamp_enabled",
        "authenticated_identity_enabled", "consensus_enabled", "approval_enabled",
        "efficacy_claims_enabled", "promotion_enabled", "scoring_enabled", "alerts_enabled",
        "options_routing_enabled", "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != expected_authority or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeBundleAuditConfigError("Phase 7N authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeBundleAuditConfig(MappingProxyType(frozen), canonical_hash(raw))


class ReviewedRangeBundleAuditRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def audit(
        self, *, export_id: str, verified_at: datetime,
        audit_config: ReviewedRangeBundleAuditConfig,
        bundle_config: ReviewedRangeBundleConfig,
        source_config: RangeEvidenceBundleConfig,
    ) -> ReviewedRangeBundleAuditReceipt:
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("Phase 7N verified_at must be timezone-aware")
        record = ReviewedRangeBundleRegistry(self.repository).load(export_id, bundle_config)
        actual_hash: str | None = None
        reasons: tuple[str, ...] = ()
        try:
            content = Path(record.output_path).read_bytes()
            actual_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
            if actual_hash != record.artifact_hash or len(content) != record.artifact_bytes:
                raise ValueError("artifact bytes do not match local export")
            verification = verify_reviewed_range_bundle(
                record.output_path, bundle_config, source_config
            )
            if verification.reviewed_bundle_id != record.reviewed_bundle_id:
                raise ValueError("verified identity does not match local export")
        except (OSError, ValueError):
            reasons = ("REVIEWED_BUNDLE_VERIFICATION_FAILED",)
        status = (
            ReviewedRangeBundleAuditStatus.VERIFIED
            if not reasons
            else ReviewedRangeBundleAuditStatus.FAILED
        )
        identity = (
            export_id, record.reviewed_bundle_id, verified_at, status, record.artifact_hash,
            actual_hash, reasons, audit_config.config_hash, source_config.config_hash,
        )
        receipt = ReviewedRangeBundleAuditReceipt(
            deterministic_id("reviewed_range_bundle_verification", identity), export_id,
            record.reviewed_bundle_id, verified_at, status, record.artifact_hash, actual_hash,
            reasons, audit_config.config_hash, source_config.config_hash,
        )
        self.persist(receipt)
        return receipt

    def persist(self, receipt: ReviewedRangeBundleAuditReceipt) -> bool:
        payload_hash = canonical_hash(receipt)
        values = (
            receipt.verification_id, receipt.reviewed_bundle_export_id,
            receipt.reviewed_bundle_id, receipt.verified_at.isoformat(), receipt.status.value,
            receipt.expected_hash, receipt.actual_hash, canonical_json(receipt.reasons),
            receipt.config_hash, receipt.source_config_hash, canonical_json(receipt), payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_bundle_verifications
               (verification_id, reviewed_bundle_export_id, reviewed_bundle_id, verified_at,
                status, expected_hash, actual_hash, reasons_json, config_hash, source_config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                "SELECT payload_hash FROM reviewed_range_bundle_verifications "
                "WHERE verification_id = ?",
                (receipt.verification_id,),
            ).fetchone()
            if row != (payload_hash,):
                raise ValueError("conflicting Phase 7N verification receipt")
            return False
        self.repository.connection.commit()
        return True

    def status(self, export_id: str) -> tuple[str | None, int]:
        rows = self.repository.connection.execute(
            """SELECT status, payload_json, payload_hash
               FROM reviewed_range_bundle_verifications WHERE reviewed_bundle_export_id = ?
               ORDER BY verified_at, verification_id""",
            (export_id,),
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row[1]))
            except json.JSONDecodeError as error:
                raise ValueError("stored Phase 7N verification is corrupt") from error
            if not isinstance(payload, dict) or canonical_hash(payload) != str(row[2]) \
                    or payload.get("status") != row[0] \
                    or payload.get("reviewed_bundle_export_id") != export_id:
                raise ValueError("stored Phase 7N verification is corrupt")
        return (None if not rows else str(rows[-1][0]), len(rows))
