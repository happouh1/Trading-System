"""Offline Phase 7S notification intents for validated Phase 7R incident events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.reviewed_range_catalog_export_incident import (
    ReviewedRangeCatalogExportIncidentEvent,
    ReviewedRangeCatalogExportIncidentEventType,
    ReviewedRangeCatalogExportIncidentRegistry,
    ReviewedRangeCatalogExportIncidentState,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "LOCAL_OUTBOX_INTENT_ONLY_NO_DELIVERY_ATTEMPT",
    "NO_OPERATOR_NOTE_OR_AUTHENTICATED_RECIPIENT_INCLUDED",
    "SOURCE_TIME_IS_CALLER_ASSERTED_AND_UNTRUSTED",
    "NO_QUARANTINE_APPROVAL_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogIncidentNotificationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationIntent:
    notification_intent_id: str
    incident_id: str
    incident_event_id: str
    catalog_export_id: str
    source_verification_id: str
    occurred_at: datetime
    event_type: ReviewedRangeCatalogExportIncidentEventType
    incident_state: ReviewedRangeCatalogExportIncidentState
    route: str
    delivery_attempt_count: int
    config_hash: str
    notification_version: str = "7S.1.0"
    network_used: bool = False
    delivery_attempted: bool = False
    recipient_authenticated: bool = False
    quarantine_enforced: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
            or self.route != "LOCAL_OPERATOR_OUTBOX"
            or self.delivery_attempt_count != 0
            or self.notification_version != "7S.1.0"
            or self.network_used
            or self.delivery_attempted
            or self.recipient_authenticated
            or self.quarantine_enforced
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7S notification intent is invalid")


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationSummary:
    incident_id: str
    catalog_export_id: str
    intent_count: int
    event_types: tuple[ReviewedRangeCatalogExportIncidentEventType, ...]
    delivery_attempt_count: int


def load_reviewed_range_catalog_incident_notification_config(
    path: str | Path,
) -> ReviewedRangeCatalogIncidentNotificationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "notification_version", "source", "route", "materialization", "delivery_policy",
        "content_policy", "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogIncidentNotificationConfigError(
            "Phase 7S configuration keys are invalid"
        )
    if (
        raw["notification_version"] != "7S.1.0"
        or raw["source"] != "VALIDATED_PHASE7R_INCIDENT_EVENTS"
        or raw["route"] != "LOCAL_OPERATOR_OUTBOX"
        or raw["materialization"] != "ONE_INTENT_PER_EXACT_INCIDENT_EVENT"
        or raw["delivery_policy"] != "NONE_OFFLINE_ONLY"
        or raw["content_policy"] != "IDENTIFIERS_AND_STATES_ONLY_NO_OPERATOR_NOTE"
    ):
        raise ReviewedRangeCatalogIncidentNotificationConfigError("Phase 7S policy is invalid")
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "delivery_enabled", "retry_enabled", "escalation_enabled",
        "signature_enabled", "trusted_timestamp_enabled", "authenticated_recipient_enabled",
        "artifact_mutation_enabled", "artifact_deletion_enabled",
        "quarantine_enforcement_enabled", "approval_enabled", "efficacy_claims_enabled",
        "promotion_enabled", "scoring_enabled", "options_routing_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogIncidentNotificationConfigError(
            "Phase 7S authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogIncidentNotificationConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


class ReviewedRangeCatalogIncidentNotificationRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.incident_registry = ReviewedRangeCatalogExportIncidentRegistry(repository)

    def materialize(
        self, incident_id: str, config: ReviewedRangeCatalogIncidentNotificationConfig
    ) -> tuple[ReviewedRangeCatalogIncidentNotificationIntent, ...]:
        events = self.incident_registry.history(incident_id)
        intents = tuple(self._from_event(event, config) for event in events)
        for intent in intents:
            self.persist(intent)
        return intents

    def persist(self, intent: ReviewedRangeCatalogIncidentNotificationIntent) -> bool:
        payload_hash = canonical_hash(intent)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_catalog_incident_notification_intents
               (notification_intent_id, incident_id, incident_event_id, catalog_export_id,
                source_verification_id, occurred_at, event_type, incident_state, route,
                delivery_attempt_count, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                intent.notification_intent_id, intent.incident_id, intent.incident_event_id,
                intent.catalog_export_id, intent.source_verification_id,
                intent.occurred_at.isoformat(), intent.event_type.value,
                intent.incident_state.value, intent.route, intent.delivery_attempt_count,
                intent.config_hash, canonical_json(intent), payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self._load(intent.notification_intent_id)
            if stored != intent:
                raise ValueError("conflicting Phase 7S notification intent")
            return False
        self.repository.connection.commit()
        return True

    def status(
        self, incident_id: str, config: ReviewedRangeCatalogIncidentNotificationConfig
    ) -> ReviewedRangeCatalogIncidentNotificationSummary:
        actual = self.load(incident_id, config)
        return ReviewedRangeCatalogIncidentNotificationSummary(
            incident_id, actual[0].catalog_export_id, len(actual),
            tuple(intent.event_type for intent in actual), 0,
        )

    def load(
        self, incident_id: str, config: ReviewedRangeCatalogIncidentNotificationConfig
    ) -> tuple[ReviewedRangeCatalogIncidentNotificationIntent, ...]:
        events = self.incident_registry.history(incident_id)
        expected = tuple(self._from_event(event, config) for event in events)
        rows = self.repository.connection.execute(
            """SELECT notification_intent_id
               FROM reviewed_range_catalog_incident_notification_intents
               WHERE incident_id = ? AND config_hash = ?
               ORDER BY occurred_at, notification_intent_id""",
            (incident_id, config.config_hash),
        ).fetchall()
        actual = tuple(self._load(str(row[0])) for row in rows)
        if actual != expected:
            raise ValueError("Phase 7S notification intent set is incomplete or corrupt")
        return actual

    @staticmethod
    def _from_event(
        event: ReviewedRangeCatalogExportIncidentEvent,
        config: ReviewedRangeCatalogIncidentNotificationConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationIntent:
        identity = (event.incident_event_id, config.config_hash)
        return ReviewedRangeCatalogIncidentNotificationIntent(
            deterministic_id("reviewed_range_catalog_incident_notification", identity),
            event.incident_id, event.incident_event_id, event.catalog_export_id,
            event.source_verification_id, event.occurred_at, event.event_type, event.new_state,
            "LOCAL_OPERATOR_OUTBOX", 0, config.config_hash,
        )

    def _load(self, intent_id: str) -> ReviewedRangeCatalogIncidentNotificationIntent:
        row = self.repository.connection.execute(
            """SELECT incident_id, incident_event_id, catalog_export_id,
                      source_verification_id, occurred_at, event_type, incident_state, route,
                      delivery_attempt_count, config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_incident_notification_intents
               WHERE notification_intent_id = ?""",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7S notification intent")
        try:
            payload = json.loads(str(row[10]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7S notification intent is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[11]):
            raise ValueError("stored Phase 7S notification intent is corrupt")
        intent = _notification_intent(payload)
        columns = (
            intent.incident_id, intent.incident_event_id, intent.catalog_export_id,
            intent.source_verification_id, intent.occurred_at.isoformat(),
            intent.event_type.value, intent.incident_state.value, intent.route,
            intent.delivery_attempt_count, intent.config_hash,
        )
        if intent.notification_intent_id != intent_id or columns != tuple(row[:10]):
            raise ValueError("stored Phase 7S notification intent is corrupt")
        return intent


def _notification_intent(
    payload: Mapping[str, object]
) -> ReviewedRangeCatalogIncidentNotificationIntent:
    required = {
        field for field in ReviewedRangeCatalogIncidentNotificationIntent.__dataclass_fields__
    } | {"__type__"}
    strings = (
        "notification_intent_id", "incident_id", "incident_event_id", "catalog_export_id",
        "source_verification_id", "route", "config_hash", "notification_version",
    )
    false_fields = (
        "network_used", "delivery_attempted", "recipient_authenticated",
        "quarantine_enforced", "approval_granted", "promotion_authority",
    )
    disclosures = payload.get("disclosures")
    if (
        set(payload) != required
        or payload.get("__type__") != "ReviewedRangeCatalogIncidentNotificationIntent"
        or not all(isinstance(payload.get(key), str) for key in strings)
        or payload.get("delivery_attempt_count") != 0
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7S notification intent is corrupt")
    try:
        event_type = ReviewedRangeCatalogExportIncidentEventType(str(payload["event_type"]))
        state = ReviewedRangeCatalogExportIncidentState(str(payload["incident_state"]))
    except ValueError as error:
        raise ValueError("stored Phase 7S notification intent is corrupt") from error
    intent = ReviewedRangeCatalogIncidentNotificationIntent(
        str(payload["notification_intent_id"]), str(payload["incident_id"]),
        str(payload["incident_event_id"]), str(payload["catalog_export_id"]),
        str(payload["source_verification_id"]),
        _canonical_datetime(payload.get("occurred_at")), event_type, state,
        str(payload["route"]), 0, str(payload["config_hash"]),
        str(payload["notification_version"]), False, False, False, False, False, False,
        tuple(disclosures),
    )
    if intent.notification_intent_id != deterministic_id(
        "reviewed_range_catalog_incident_notification",
        (intent.incident_event_id, intent.config_hash),
    ):
        raise ValueError("stored Phase 7S notification intent is corrupt")
    return intent


def _canonical_datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("stored Phase 7S notification intent is corrupt")
    timestamp = value["__datetime__"]
    if not isinstance(timestamp, str):
        raise ValueError("stored Phase 7S notification intent is corrupt")
    result = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored Phase 7S notification intent is corrupt")
    return result
