"""Atomic Phase 7T exports of complete validated Phase 7S notification intents."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.reviewed_range_catalog_incident_notification import (
    ReviewedRangeCatalogIncidentNotificationConfig,
    ReviewedRangeCatalogIncidentNotificationIntent,
    ReviewedRangeCatalogIncidentNotificationRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "LOCAL_EXPORT_IS_NOT_A_DELIVERY_ATTEMPT_OR_RECEIPT",
    "EXPORT_CONTAINS_NO_OPERATOR_ID_OR_NOTE",
    "CONTENT_INTEGRITY_IS_UNSIGNED_AND_HAS_NO_TRUSTED_TIME",
    "NO_QUARANTINE_APPROVAL_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogIncidentNotificationExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportReceipt:
    notification_export_id: str
    incident_id: str
    opening_incident_event_id: str
    catalog_export_id: str
    output_path: str
    content_hash: str
    byte_count: int
    intent_count: int
    notification_config_hash: str
    export_config_hash: str
    export_version: str = "7T.1.0"
    network_used: bool = False
    delivery_attempted: bool = False
    signed: bool = False
    trusted_timestamp: bool = False
    recipient_authenticated: bool = False
    quarantine_enforced: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            not self.notification_export_id
            or not self.incident_id
            or not self.opening_incident_event_id
            or not self.catalog_export_id
            or not self.output_path
            or self.byte_count <= 0
            or self.intent_count <= 0
            or self.export_version != "7T.1.0"
            or self.network_used
            or self.delivery_attempted
            or self.signed
            or self.trusted_timestamp
            or self.recipient_authenticated
            or self.quarantine_enforced
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7T notification export receipt is invalid")


def load_reviewed_range_catalog_incident_notification_export_config(
    path: str | Path,
) -> ReviewedRangeCatalogIncidentNotificationExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "export_version", "source", "format", "write_policy", "verification",
        "content_policy", "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogIncidentNotificationExportConfigError(
            "Phase 7T configuration keys are invalid"
        )
    if (
        raw["export_version"] != "7T.1.0"
        or raw["source"] != "COMPLETE_VALIDATED_PHASE7S_INTENT_SET"
        or raw["format"] != "CANONICAL_JSON_UTF8_LF"
        or raw["write_policy"] != "ATOMIC_SAME_DIRECTORY_REPLACE"
        or raw["verification"] != "SHA256_BYTES_AND_FULL_SOURCE_REVALIDATION"
        or raw["content_policy"] != "IDENTIFIERS_AND_STATES_ONLY_NO_OPERATOR_NOTE"
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportConfigError(
            "Phase 7T export policy is invalid"
        )
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "delivery_enabled", "retry_enabled", "escalation_enabled",
        "signature_enabled", "trusted_timestamp_enabled", "authenticated_recipient_enabled",
        "artifact_mutation_enabled", "quarantine_enforcement_enabled", "approval_enabled",
        "efficacy_claims_enabled", "promotion_enabled", "scoring_enabled",
        "options_routing_enabled", "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportConfigError(
            "Phase 7T authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogIncidentNotificationExportConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


def write_reviewed_range_catalog_incident_notification_export(
    *, intents: tuple[ReviewedRangeCatalogIncidentNotificationIntent, ...],
    output: str | Path, config: ReviewedRangeCatalogIncidentNotificationExportConfig,
) -> ReviewedRangeCatalogIncidentNotificationExportReceipt:
    if not intents:
        raise ValueError("Phase 7T requires at least one notification intent")
    incident_id = intents[0].incident_id
    catalog_export_id = intents[0].catalog_export_id
    if any(
        intent.incident_id != incident_id or intent.catalog_export_id != catalog_export_id
        for intent in intents
    ):
        raise ValueError("Phase 7T notification intents do not share one incident")
    target = Path(output).resolve()
    if not target.parent.is_dir():
        raise ValueError("Phase 7T output parent does not exist")
    content = f"{canonical_json(_manifest(intents))}\n".encode()
    content_hash = _byte_hash(content)
    identity = (
        incident_id, intents[0].incident_event_id, catalog_export_id, str(target), content_hash,
        intents[0].config_hash, config.config_hash,
    )
    receipt = ReviewedRangeCatalogIncidentNotificationExportReceipt(
        deterministic_id("reviewed_range_catalog_incident_notification_export", identity),
        incident_id, intents[0].incident_event_id, catalog_export_id, str(target),
        content_hash, len(content), len(intents), intents[0].config_hash, config.config_hash,
    )
    _atomic_replace(target, content)
    return receipt


class ReviewedRangeCatalogIncidentNotificationExportRegistry:
    def __init__(
        self, repository: SQLiteRepository,
        notification_registry: ReviewedRangeCatalogIncidentNotificationRegistry,
    ) -> None:
        self.repository = repository
        self.notification_registry = notification_registry

    def persist(
        self, receipt: ReviewedRangeCatalogIncidentNotificationExportReceipt,
        notification_config: ReviewedRangeCatalogIncidentNotificationConfig,
    ) -> bool:
        intents = self.notification_registry.load(receipt.incident_id, notification_config)
        self._match_source(receipt, intents)
        payload_hash = canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_catalog_incident_notification_exports
               (notification_export_id, incident_id, opening_incident_event_id,
                catalog_export_id, output_path, content_hash, byte_count, intent_count,
                notification_config_hash, export_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.notification_export_id, receipt.incident_id,
                receipt.opening_incident_event_id, receipt.catalog_export_id,
                receipt.output_path, receipt.content_hash, receipt.byte_count,
                receipt.intent_count, receipt.notification_config_hash,
                receipt.export_config_hash, canonical_json(receipt), payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self._load(receipt.notification_export_id)
            if stored != receipt:
                raise ValueError("conflicting Phase 7T notification export")
            return False
        self.repository.connection.commit()
        return True

    def verify(
        self, export_id: str,
        config: ReviewedRangeCatalogIncidentNotificationExportConfig,
        notification_config: ReviewedRangeCatalogIncidentNotificationConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportReceipt:
        receipt = self._load(export_id)
        if (
            receipt.export_config_hash != config.config_hash
            or receipt.notification_config_hash != notification_config.config_hash
        ):
            raise ValueError("Phase 7T export configuration is inconsistent")
        expected_id = deterministic_id(
            "reviewed_range_catalog_incident_notification_export",
            (
                receipt.incident_id, receipt.opening_incident_event_id,
                receipt.catalog_export_id, receipt.output_path, receipt.content_hash,
                receipt.notification_config_hash, receipt.export_config_hash,
            ),
        )
        if expected_id != export_id:
            raise ValueError("Phase 7T export identity is inconsistent")
        intents = self.notification_registry.load(receipt.incident_id, notification_config)
        self._match_source(receipt, intents)
        target = Path(receipt.output_path)
        if not target.is_file():
            raise ValueError("Phase 7T notification export is missing")
        content = target.read_bytes()
        expected = f"{canonical_json(_manifest(intents))}\n".encode()
        if (
            content != expected
            or len(content) != receipt.byte_count
            or _byte_hash(content) != receipt.content_hash
        ):
            raise ValueError("Phase 7T notification export content is corrupt")
        return receipt

    def _load(self, export_id: str) -> ReviewedRangeCatalogIncidentNotificationExportReceipt:
        row = self.repository.connection.execute(
            """SELECT incident_id, opening_incident_event_id, catalog_export_id,
                      output_path, content_hash, byte_count, intent_count,
                      notification_config_hash, export_config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_incident_notification_exports
               WHERE notification_export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7T notification export")
        try:
            payload = json.loads(str(row[9]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7T notification export is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[10]):
            raise ValueError("stored Phase 7T notification export is corrupt")
        receipt = _receipt(payload)
        columns = (
            receipt.incident_id, receipt.opening_incident_event_id,
            receipt.catalog_export_id, receipt.output_path, receipt.content_hash,
            receipt.byte_count, receipt.intent_count, receipt.notification_config_hash,
            receipt.export_config_hash,
        )
        if receipt.notification_export_id != export_id or columns != tuple(row[:9]):
            raise ValueError("stored Phase 7T notification export is corrupt")
        return receipt

    @staticmethod
    def _match_source(
        receipt: ReviewedRangeCatalogIncidentNotificationExportReceipt,
        intents: tuple[ReviewedRangeCatalogIncidentNotificationIntent, ...],
    ) -> None:
        if (
            not intents
            or receipt.opening_incident_event_id != intents[0].incident_event_id
            or receipt.catalog_export_id != intents[0].catalog_export_id
            or receipt.intent_count != len(intents)
            or receipt.notification_config_hash != intents[0].config_hash
        ):
            raise ValueError("Phase 7T receipt does not match its Phase 7S source")


def _manifest(
    intents: tuple[ReviewedRangeCatalogIncidentNotificationIntent, ...]
) -> dict[str, object]:
    return {
        "schema_version": "7T.1.0",
        "incident_id": intents[0].incident_id,
        "catalog_export_id": intents[0].catalog_export_id,
        "notification_intents": intents,
        "intent_count": len(intents),
        "route": "LOCAL_OPERATOR_OUTBOX",
        "delivery_attempt_count": 0,
        "disclosures": _DISCLOSURES,
        "network_used": False,
        "delivery_attempted": False,
        "approval_granted": False,
        "promotion_authority": False,
    }


def _receipt(
    payload: Mapping[str, object]
) -> ReviewedRangeCatalogIncidentNotificationExportReceipt:
    required = {
        field
        for field in ReviewedRangeCatalogIncidentNotificationExportReceipt.__dataclass_fields__
    } | {"__type__"}
    strings = (
        "notification_export_id", "incident_id", "opening_incident_event_id",
        "catalog_export_id", "output_path", "content_hash", "notification_config_hash",
        "export_config_hash", "export_version",
    )
    false_fields = (
        "network_used", "delivery_attempted", "signed", "trusted_timestamp",
        "recipient_authenticated", "quarantine_enforced", "approval_granted",
        "promotion_authority",
    )
    byte_count = payload.get("byte_count")
    intent_count = payload.get("intent_count")
    disclosures = payload.get("disclosures")
    if (
        set(payload) != required
        or payload.get("__type__")
        != "ReviewedRangeCatalogIncidentNotificationExportReceipt"
        or not all(isinstance(payload.get(key), str) for key in strings)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or isinstance(intent_count, bool)
        or not isinstance(intent_count, int)
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7T notification export is corrupt")
    return ReviewedRangeCatalogIncidentNotificationExportReceipt(
        str(payload["notification_export_id"]), str(payload["incident_id"]),
        str(payload["opening_incident_event_id"]), str(payload["catalog_export_id"]),
        str(payload["output_path"]), str(payload["content_hash"]), byte_count, intent_count,
        str(payload["notification_config_hash"]), str(payload["export_config_hash"]),
        str(payload["export_version"]), False, False, False, False, False, False, False, False,
        tuple(disclosures),
    )


def _atomic_replace(target: Path, content: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", delete=False, dir=target.parent, prefix=".incident-notification-", suffix=".tmp"
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _byte_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
