"""Append-only Phase 7Q verification receipts for Phase 7P local exports."""

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
from trading_system.reporting.reviewed_range_bundle import ReviewedRangeBundleConfig
from trading_system.reporting.reviewed_range_catalog import ReviewedRangeCatalogConfig
from trading_system.reporting.reviewed_range_catalog_export import (
    ReviewedRangeCatalogExportConfig,
    ReviewedRangeCatalogExportRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "CALLER_ASSERTED_TIME_IS_NOT_A_TRUSTED_TIMESTAMP",
    "LOCAL_EXPORT_VERIFICATION_IS_NOT_A_SIGNATURE_OR_APPROVAL",
    "CATALOG_MEMBERSHIP_IS_NOT_A_COMPLETE_OR_RANKED_POPULATION",
    "NO_CONSENSUS_EFFICACY_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogExportAuditConfigError(ValueError):
    pass


class ReviewedRangeCatalogExportAuditStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportAuditConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportAuditReceipt:
    verification_id: str
    catalog_export_id: str
    catalog_id: str
    verified_at: datetime
    status: ReviewedRangeCatalogExportAuditStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    config_hash: str
    export_config_hash: str
    catalog_config_hash: str
    bundle_config_hash: str
    source_config_hash: str
    verification_version: str = "7Q.1.0"
    trusted_timestamp: bool = False
    signed: bool = False
    membership_complete: bool = False
    ranking_performed: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() is None
            or self.verification_version != "7Q.1.0"
            or self.trusted_timestamp
            or self.signed
            or self.membership_complete
            or self.ranking_performed
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7Q verification receipt is invalid")


def load_reviewed_range_catalog_export_audit_config(
    path: str | Path,
) -> ReviewedRangeCatalogExportAuditConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "verification_version", "source", "verification", "failure_policy", "timestamp",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogExportAuditConfigError("Phase 7Q configuration keys are invalid")
    if (
        raw["verification_version"] != "7Q.1.0"
        or raw["source"] != "PERSISTED_PHASE7P_LOCAL_EXPORT"
        or raw["verification"] != "REHASH_AND_FULL_SOURCE_REVALIDATION"
        or raw["failure_policy"] != "APPEND_RECEIPT_AND_FAIL_CLOSED"
        or raw["timestamp"] != "CALLER_ASSERTED_UNTRUSTED_AWARE"
    ):
        raise ReviewedRangeCatalogExportAuditConfigError("Phase 7Q policy is invalid")
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "signature_enabled", "trusted_timestamp_enabled",
        "authenticated_identity_enabled", "consensus_enabled", "completeness_claim_enabled",
        "ranking_enabled", "approval_enabled", "efficacy_claims_enabled", "promotion_enabled",
        "scoring_enabled", "alerts_enabled", "options_routing_enabled", "broker_writes_enabled",
        "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogExportAuditConfigError("Phase 7Q authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogExportAuditConfig(MappingProxyType(frozen), canonical_hash(raw))


class ReviewedRangeCatalogExportAuditRegistry:
    def __init__(
        self, repository: SQLiteRepository,
        export_registry: ReviewedRangeCatalogExportRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.export_registry = export_registry

    def audit(
        self, *, export_id: str, verified_at: datetime,
        audit_config: ReviewedRangeCatalogExportAuditConfig,
        export_config: ReviewedRangeCatalogExportConfig,
        catalog_config: ReviewedRangeCatalogConfig,
        bundle_config: ReviewedRangeBundleConfig,
        source_config: RangeEvidenceBundleConfig,
    ) -> ReviewedRangeCatalogExportAuditReceipt:
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("Phase 7Q verified_at must be timezone-aware")
        row = self.repository.connection.execute(
            """SELECT exports.catalog_id, exports.output_path, exports.content_hash,
                      exports.export_config_hash, exports.catalog_config_hash,
                      catalogs.cataloged_at
               FROM reviewed_range_catalog_exports AS exports
               JOIN reviewed_range_bundle_catalogs AS catalogs
                 ON catalogs.catalog_id = exports.catalog_id
               WHERE exports.catalog_export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7P catalog export")
        catalog_id = str(row[0])
        expected_hash = str(row[2])
        cataloged_at = datetime.fromisoformat(str(row[5]).replace("Z", "+00:00"))
        if verified_at < cataloged_at:
            raise ValueError("Phase 7Q verification cannot predate its source catalog")
        actual_hash: str | None = None
        reasons: tuple[str, ...] = ()
        try:
            if self.export_registry is None:
                raise ValueError("Phase 7Q source verifier is unavailable")
            content = Path(str(row[1])).read_bytes()
            actual_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
            receipt = self.export_registry.verify(export_id, export_config)
            if receipt.catalog_id != catalog_id or actual_hash != expected_hash:
                raise ValueError("Phase 7Q export identity mismatch")
        except (OSError, ValueError):
            reasons = ("REVIEWED_CATALOG_EXPORT_VERIFICATION_FAILED",)
        status = (
            ReviewedRangeCatalogExportAuditStatus.VERIFIED
            if not reasons
            else ReviewedRangeCatalogExportAuditStatus.FAILED
        )
        identity = (
            export_id, catalog_id, verified_at, status, expected_hash, actual_hash, reasons,
            audit_config.config_hash, export_config.config_hash, catalog_config.config_hash,
            bundle_config.config_hash, source_config.config_hash,
        )
        result = ReviewedRangeCatalogExportAuditReceipt(
            deterministic_id("reviewed_range_catalog_export_verification", identity),
            export_id, catalog_id, verified_at, status, expected_hash, actual_hash, reasons,
            audit_config.config_hash, export_config.config_hash, catalog_config.config_hash,
            bundle_config.config_hash, source_config.config_hash,
        )
        self.persist(result)
        return result

    def persist(self, receipt: ReviewedRangeCatalogExportAuditReceipt) -> bool:
        payload_hash = canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_catalog_export_verifications
               (verification_id, catalog_export_id, catalog_id, verified_at, status,
                expected_hash, actual_hash, reasons_json, config_hash, export_config_hash,
                catalog_config_hash, bundle_config_hash, source_config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.verification_id, receipt.catalog_export_id, receipt.catalog_id,
                receipt.verified_at.isoformat(), receipt.status.value, receipt.expected_hash,
                receipt.actual_hash, canonical_json(receipt.reasons), receipt.config_hash,
                receipt.export_config_hash, receipt.catalog_config_hash,
                receipt.bundle_config_hash, receipt.source_config_hash,
                canonical_json(receipt), payload_hash,
            ),
        )
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                "SELECT payload_hash FROM reviewed_range_catalog_export_verifications "
                "WHERE verification_id = ?", (receipt.verification_id,),
            ).fetchone()
            if row != (payload_hash,):
                raise ValueError("conflicting Phase 7Q verification receipt")
            return False
        self.repository.connection.commit()
        return True

    def status(self, export_id: str) -> tuple[str | None, int]:
        rows = self.repository.connection.execute(
            """SELECT verification_id, catalog_id, verified_at, status, expected_hash,
                      actual_hash, reasons_json, config_hash, export_config_hash,
                      catalog_config_hash, bundle_config_hash, source_config_hash,
                      payload_json, payload_hash
               FROM reviewed_range_catalog_export_verifications
               WHERE catalog_export_id = ? ORDER BY verified_at, verification_id""",
            (export_id,),
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(str(row[12]))
                reasons = json.loads(str(row[6]))
            except json.JSONDecodeError as error:
                raise ValueError("stored Phase 7Q verification is corrupt") from error
            if not isinstance(payload, dict) or canonical_hash(payload) != str(row[13]):
                raise ValueError("stored Phase 7Q verification is corrupt")
            receipt = _audit_receipt(payload)
            expected_columns = (
                receipt.verification_id, receipt.catalog_id, receipt.verified_at.isoformat(),
                receipt.status.value, receipt.expected_hash, receipt.actual_hash,
                canonical_json(receipt.reasons), receipt.config_hash,
                receipt.export_config_hash, receipt.catalog_config_hash,
                receipt.bundle_config_hash, receipt.source_config_hash,
            )
            if (
                receipt.catalog_export_id != export_id
                or expected_columns
                != (*tuple(row[:6]), str(row[6]), *tuple(row[7:12]))
                or reasons != list(receipt.reasons)
                or receipt.verification_id
                != deterministic_id(
                    "reviewed_range_catalog_export_verification",
                    (
                        receipt.catalog_export_id, receipt.catalog_id, receipt.verified_at,
                        receipt.status, receipt.expected_hash, receipt.actual_hash,
                        receipt.reasons, receipt.config_hash, receipt.export_config_hash,
                        receipt.catalog_config_hash, receipt.bundle_config_hash,
                        receipt.source_config_hash,
                    ),
                )
            ):
                raise ValueError("stored Phase 7Q verification is corrupt")
        return (None if not rows else str(rows[-1][3]), len(rows))

    def load(self, verification_id: str) -> ReviewedRangeCatalogExportAuditReceipt:
        row = self.repository.connection.execute(
            """SELECT catalog_export_id, catalog_id, verified_at, status, expected_hash,
                      actual_hash, reasons_json, config_hash, export_config_hash,
                      catalog_config_hash, bundle_config_hash, source_config_hash,
                      payload_json, payload_hash
               FROM reviewed_range_catalog_export_verifications
               WHERE verification_id = ?""",
            (verification_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7Q verification receipt")
        try:
            payload = json.loads(str(row[12]))
            reasons = json.loads(str(row[6]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7Q verification is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[13]):
            raise ValueError("stored Phase 7Q verification is corrupt")
        receipt = _audit_receipt(payload)
        expected_columns = (
            receipt.catalog_export_id, receipt.catalog_id, receipt.verified_at.isoformat(),
            receipt.status.value, receipt.expected_hash, receipt.actual_hash,
            canonical_json(receipt.reasons), receipt.config_hash,
            receipt.export_config_hash, receipt.catalog_config_hash,
            receipt.bundle_config_hash, receipt.source_config_hash,
        )
        if (
            receipt.verification_id != verification_id
            or expected_columns != tuple(row[:12])
            or reasons != list(receipt.reasons)
            or receipt.verification_id
            != deterministic_id(
                "reviewed_range_catalog_export_verification",
                (
                    receipt.catalog_export_id, receipt.catalog_id, receipt.verified_at,
                    receipt.status, receipt.expected_hash, receipt.actual_hash,
                    receipt.reasons, receipt.config_hash, receipt.export_config_hash,
                    receipt.catalog_config_hash, receipt.bundle_config_hash,
                    receipt.source_config_hash,
                ),
            )
        ):
            raise ValueError("stored Phase 7Q verification is corrupt")
        return receipt


def _audit_receipt(payload: Mapping[str, object]) -> ReviewedRangeCatalogExportAuditReceipt:
    required = {
        field for field in ReviewedRangeCatalogExportAuditReceipt.__dataclass_fields__
    } | {"__type__"}
    string_fields = (
        "verification_id", "catalog_export_id", "catalog_id", "expected_hash", "config_hash",
        "export_config_hash", "catalog_config_hash", "bundle_config_hash", "source_config_hash",
        "verification_version",
    )
    reasons = payload.get("reasons")
    disclosures = payload.get("disclosures")
    false_fields = (
        "trusted_timestamp", "signed", "membership_complete", "ranking_performed",
        "approval_granted", "promotion_authority",
    )
    if (
        set(payload) != required
        or payload.get("__type__") != "ReviewedRangeCatalogExportAuditReceipt"
        or not all(isinstance(payload.get(key), str) for key in string_fields)
        or (payload.get("actual_hash") is not None
        and not isinstance(payload.get("actual_hash"), str))
        or not isinstance(reasons, list)
        or not all(isinstance(item, str) for item in reasons)
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7Q verification is corrupt")
    try:
        status = ReviewedRangeCatalogExportAuditStatus(str(payload["status"]))
    except ValueError as error:
        raise ValueError("stored Phase 7Q verification is corrupt") from error
    return ReviewedRangeCatalogExportAuditReceipt(
        str(payload["verification_id"]), str(payload["catalog_export_id"]),
        str(payload["catalog_id"]), _canonical_datetime(payload.get("verified_at")), status,
        str(payload["expected_hash"]),
        None if payload.get("actual_hash") is None else str(payload["actual_hash"]),
        tuple(reasons), str(payload["config_hash"]), str(payload["export_config_hash"]),
        str(payload["catalog_config_hash"]), str(payload["bundle_config_hash"]),
        str(payload["source_config_hash"]), str(payload["verification_version"]),
        False, False, False, False, False, False, tuple(disclosures),
    )


def _canonical_datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("stored Phase 7Q verification is corrupt")
    timestamp = value["__datetime__"]
    if not isinstance(timestamp, str):
        raise ValueError("stored Phase 7Q verification is corrupt")
    result = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored Phase 7Q verification is corrupt")
    return result
