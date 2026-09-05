"""Append-only Phase 7U verification receipts for Phase 7T local exports."""

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
from trading_system.reporting.reviewed_range_catalog_incident_notification import (
    ReviewedRangeCatalogIncidentNotificationConfig,
)
from trading_system.reporting.reviewed_range_catalog_incident_notification_export import (
    ReviewedRangeCatalogIncidentNotificationExportConfig,
    ReviewedRangeCatalogIncidentNotificationExportRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "CALLER_ASSERTED_TIME_IS_NOT_A_TRUSTED_TIMESTAMP",
    "LOCAL_FILE_VERIFICATION_IS_NOT_DELIVERY_RECIPIENT_AUTHENTICATION_OR_APPROVAL",
    "FAILED_VERIFICATION_DOES_NOT_MUTATE_OR_QUARANTINE_THE_SOURCE_ARTIFACT",
    "NO_EFFICACY_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogIncidentNotificationExportAuditConfigError(ValueError):
    pass


class ReviewedRangeCatalogIncidentNotificationExportAuditStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportAuditConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportAuditReceipt:
    verification_id: str
    notification_export_id: str
    incident_id: str
    verified_at: datetime
    status: ReviewedRangeCatalogIncidentNotificationExportAuditStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    config_hash: str
    export_config_hash: str
    notification_config_hash: str
    verification_version: str = "7U.1.0"
    network_used: bool = False
    delivery_attempted: bool = False
    signed: bool = False
    trusted_timestamp: bool = False
    identity_authenticated: bool = False
    recipient_authenticated: bool = False
    artifact_mutated: bool = False
    quarantine_enforced: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            not self.verification_id
            or not self.notification_export_id
            or not self.incident_id
            or self.verified_at.tzinfo is None
            or self.verified_at.utcoffset() is None
            or self.verification_version != "7U.1.0"
            or self.network_used
            or self.delivery_attempted
            or self.signed
            or self.trusted_timestamp
            or self.identity_authenticated
            or self.recipient_authenticated
            or self.artifact_mutated
            or self.quarantine_enforced
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7U verification receipt is invalid")


def load_reviewed_range_catalog_incident_notification_export_audit_config(
    path: str | Path,
) -> ReviewedRangeCatalogIncidentNotificationExportAuditConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "verification_version", "source", "verification", "failure_policy", "timestamp",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogIncidentNotificationExportAuditConfigError(
            "Phase 7U configuration keys are invalid"
        )
    if (
        raw["verification_version"] != "7U.1.0"
        or raw["source"] != "PERSISTED_PHASE7T_LOCAL_EXPORT"
        or raw["verification"] != "REHASH_AND_FULL_SOURCE_REVALIDATION"
        or raw["failure_policy"] != "APPEND_RECEIPT_AND_FAIL_CLOSED"
        or raw["timestamp"] != "CALLER_ASSERTED_UNTRUSTED_AWARE"
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportAuditConfigError(
            "Phase 7U policy is invalid"
        )
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "delivery_enabled", "retry_enabled", "escalation_enabled",
        "signature_enabled", "trusted_timestamp_enabled", "authenticated_identity_enabled",
        "authenticated_recipient_enabled", "artifact_mutation_enabled",
        "quarantine_enforcement_enabled", "approval_enabled", "efficacy_claims_enabled",
        "promotion_enabled", "scoring_enabled", "options_routing_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportAuditConfigError(
            "Phase 7U authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogIncidentNotificationExportAuditConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


class ReviewedRangeCatalogIncidentNotificationExportAuditRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        export_registry: ReviewedRangeCatalogIncidentNotificationExportRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.export_registry = export_registry

    def audit(
        self,
        *,
        export_id: str,
        verified_at: datetime,
        audit_config: ReviewedRangeCatalogIncidentNotificationExportAuditConfig,
        export_config: ReviewedRangeCatalogIncidentNotificationExportConfig,
        notification_config: ReviewedRangeCatalogIncidentNotificationConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportAuditReceipt:
        if verified_at.tzinfo is None or verified_at.utcoffset() is None:
            raise ValueError("Phase 7U verified_at must be timezone-aware")
        row = self.repository.connection.execute(
            """SELECT exports.incident_id, exports.output_path, exports.content_hash,
                      exports.export_config_hash, exports.notification_config_hash,
                      MAX(events.occurred_at)
               FROM reviewed_range_catalog_incident_notification_exports AS exports
               JOIN reviewed_range_catalog_export_incident_events AS events
                 ON events.incident_id = exports.incident_id
               WHERE exports.notification_export_id = ?
               GROUP BY exports.notification_export_id""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7T notification export")
        incident_id = str(row[0])
        expected_hash = str(row[2])
        latest_event_at = datetime.fromisoformat(str(row[5]).replace("Z", "+00:00"))
        if verified_at < latest_event_at:
            raise ValueError("Phase 7U verification cannot predate its source incident history")
        actual_hash: str | None = None
        reasons: tuple[str, ...] = ()
        try:
            content = Path(str(row[1])).read_bytes()
            actual_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
            if self.export_registry is None:
                raise ValueError("Phase 7U source verifier is unavailable")
            receipt = self.export_registry.verify(export_id, export_config, notification_config)
            if receipt.incident_id != incident_id or actual_hash != expected_hash:
                raise ValueError("Phase 7U export identity mismatch")
        except (OSError, ValueError):
            reasons = ("INCIDENT_NOTIFICATION_EXPORT_VERIFICATION_FAILED",)
        status = (
            ReviewedRangeCatalogIncidentNotificationExportAuditStatus.VERIFIED
            if not reasons
            else ReviewedRangeCatalogIncidentNotificationExportAuditStatus.FAILED
        )
        identity = (
            export_id, incident_id, verified_at, status, expected_hash, actual_hash, reasons,
            audit_config.config_hash, export_config.config_hash, notification_config.config_hash,
        )
        result = ReviewedRangeCatalogIncidentNotificationExportAuditReceipt(
            deterministic_id(
                "reviewed_range_catalog_incident_notification_export_verification", identity
            ),
            export_id, incident_id, verified_at, status, expected_hash, actual_hash, reasons,
            audit_config.config_hash, export_config.config_hash,
            notification_config.config_hash,
        )
        self.persist(result)
        return result

    def persist(
        self, receipt: ReviewedRangeCatalogIncidentNotificationExportAuditReceipt
    ) -> bool:
        payload_hash = canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO
               reviewed_range_catalog_incident_notification_export_verifications
               (verification_id, notification_export_id, incident_id, verified_at, status,
                expected_hash, actual_hash, reasons_json, config_hash, export_config_hash,
                notification_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.verification_id, receipt.notification_export_id, receipt.incident_id,
                receipt.verified_at.isoformat(), receipt.status.value, receipt.expected_hash,
                receipt.actual_hash, canonical_json(receipt.reasons), receipt.config_hash,
                receipt.export_config_hash, receipt.notification_config_hash,
                canonical_json(receipt), payload_hash,
            ),
        )
        if not cursor.rowcount:
            if self.load(receipt.verification_id) != receipt:
                raise ValueError("conflicting Phase 7U verification receipt")
            return False
        self.repository.connection.commit()
        return True

    def status(self, export_id: str) -> tuple[str | None, int]:
        rows = self.repository.connection.execute(
            """SELECT verification_id FROM
               reviewed_range_catalog_incident_notification_export_verifications
               WHERE notification_export_id = ? ORDER BY verified_at, verification_id""",
            (export_id,),
        ).fetchall()
        receipts = tuple(self.load(str(row[0])) for row in rows)
        if any(receipt.notification_export_id != export_id for receipt in receipts):
            raise ValueError("stored Phase 7U verification is corrupt")
        return (None if not receipts else receipts[-1].status.value, len(receipts))

    def load(
        self, verification_id: str
    ) -> ReviewedRangeCatalogIncidentNotificationExportAuditReceipt:
        row = self.repository.connection.execute(
            """SELECT notification_export_id, incident_id, verified_at, status, expected_hash,
                      actual_hash, reasons_json, config_hash, export_config_hash,
                      notification_config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_incident_notification_export_verifications
               WHERE verification_id = ?""",
            (verification_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7U verification receipt")
        try:
            reasons = json.loads(str(row[6]))
            payload = json.loads(str(row[10]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7U verification is corrupt") from error
        if (
            not isinstance(reasons, list)
            or not isinstance(payload, dict)
            or canonical_hash(payload) != str(row[11])
        ):
            raise ValueError("stored Phase 7U verification is corrupt")
        receipt = _audit_receipt(payload)
        columns = (
            receipt.notification_export_id, receipt.incident_id,
            receipt.verified_at.isoformat(), receipt.status.value, receipt.expected_hash,
            receipt.actual_hash, canonical_json(receipt.reasons), receipt.config_hash,
            receipt.export_config_hash, receipt.notification_config_hash,
        )
        identity = (
            receipt.notification_export_id, receipt.incident_id, receipt.verified_at,
            receipt.status, receipt.expected_hash, receipt.actual_hash, receipt.reasons,
            receipt.config_hash, receipt.export_config_hash,
            receipt.notification_config_hash,
        )
        if (
            receipt.verification_id != verification_id
            or columns != tuple(row[:10])
            or reasons != list(receipt.reasons)
            or receipt.verification_id
            != deterministic_id(
                "reviewed_range_catalog_incident_notification_export_verification", identity
            )
        ):
            raise ValueError("stored Phase 7U verification is corrupt")
        return receipt


def _audit_receipt(
    payload: Mapping[str, object],
) -> ReviewedRangeCatalogIncidentNotificationExportAuditReceipt:
    required = {
        field
        for field in ReviewedRangeCatalogIncidentNotificationExportAuditReceipt.__dataclass_fields__
    } | {"__type__"}
    strings = (
        "verification_id", "notification_export_id", "incident_id", "expected_hash",
        "config_hash", "export_config_hash", "notification_config_hash",
        "verification_version",
    )
    false_fields = (
        "network_used", "delivery_attempted", "signed", "trusted_timestamp",
        "identity_authenticated", "recipient_authenticated", "artifact_mutated",
        "quarantine_enforced", "approval_granted", "promotion_authority",
    )
    reasons = payload.get("reasons")
    disclosures = payload.get("disclosures")
    if (
        set(payload) != required
        or payload.get("__type__")
        != "ReviewedRangeCatalogIncidentNotificationExportAuditReceipt"
        or not all(isinstance(payload.get(key), str) for key in strings)
        or (payload.get("actual_hash") is not None
            and not isinstance(payload.get("actual_hash"), str))
        or not isinstance(reasons, list)
        or not all(isinstance(item, str) for item in reasons)
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7U verification is corrupt")
    try:
        status = ReviewedRangeCatalogIncidentNotificationExportAuditStatus(
            str(payload["status"])
        )
    except ValueError as error:
        raise ValueError("stored Phase 7U verification is corrupt") from error
    return ReviewedRangeCatalogIncidentNotificationExportAuditReceipt(
        str(payload["verification_id"]), str(payload["notification_export_id"]),
        str(payload["incident_id"]), _canonical_datetime(payload.get("verified_at")), status,
        str(payload["expected_hash"]),
        None if payload.get("actual_hash") is None else str(payload["actual_hash"]),
        tuple(reasons), str(payload["config_hash"]), str(payload["export_config_hash"]),
        str(payload["notification_config_hash"]), str(payload["verification_version"]),
        False, False, False, False, False, False, False, False, False, False,
        tuple(disclosures),
    )


def _canonical_datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("stored Phase 7U verification is corrupt")
    timestamp = value["__datetime__"]
    if not isinstance(timestamp, str):
        raise ValueError("stored Phase 7U verification is corrupt")
    result = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored Phase 7U verification is corrupt")
    return result
