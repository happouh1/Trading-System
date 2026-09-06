"""Offline Phase 7W intents for validated Phase 7V incident events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.reviewed_range_catalog_incident_notification_export_incident import (
    ReviewedRangeCatalogIncidentNotificationExportIncidentEvent,
    ReviewedRangeCatalogIncidentNotificationExportIncidentEventType,
    ReviewedRangeCatalogIncidentNotificationExportIncidentRegistry,
    ReviewedRangeCatalogIncidentNotificationExportIncidentState,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "LOCAL_OUTBOX_INTENT_ONLY_NO_DELIVERY_ATTEMPT",
    "NO_OPERATOR_ID_NOTE_OR_AUTHENTICATED_RECIPIENT_INCLUDED",
    "SOURCE_TIME_IS_CALLER_ASSERTED_AND_UNTRUSTED",
    "NO_QUARANTINE_APPROVAL_PROMOTION_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent:
    notification_intent_id: str
    incident_id: str
    incident_event_id: str
    notification_export_id: str
    source_verification_id: str
    occurred_at: datetime
    event_type: ReviewedRangeCatalogIncidentNotificationExportIncidentEventType
    incident_state: ReviewedRangeCatalogIncidentNotificationExportIncidentState
    route: str
    delivery_attempt_count: int
    config_hash: str
    notification_version: str = "7W.1.0"
    network_used: bool = False
    delivery_attempted: bool = False
    recipient_authenticated: bool = False
    artifact_mutated: bool = False
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
            or self.notification_version != "7W.1.0"
            or self.network_used
            or self.delivery_attempted
            or self.recipient_authenticated
            or self.artifact_mutated
            or self.quarantine_enforced
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7W notification intent is invalid")


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary:
    incident_id: str
    notification_export_id: str
    intent_count: int
    event_types: tuple[
        ReviewedRangeCatalogIncidentNotificationExportIncidentEventType, ...
    ]
    delivery_attempt_count: int


def load_reviewed_range_catalog_incident_notification_export_incident_notification_config(
    path: str | Path,
) -> ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "notification_version", "source", "route", "materialization", "delivery_policy",
        "content_policy", "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError(
            "Phase 7W configuration keys are invalid"
        )
    if (
        raw["notification_version"] != "7W.1.0"
        or raw["source"] != "VALIDATED_PHASE7V_INCIDENT_EVENTS"
        or raw["route"] != "LOCAL_OPERATOR_OUTBOX"
        or raw["materialization"] != "ONE_INTENT_PER_EXACT_INCIDENT_EVENT"
        or raw["delivery_policy"] != "NONE_OFFLINE_ONLY"
        or raw["content_policy"] != "IDENTIFIERS_AND_STATES_ONLY_NO_OPERATOR_NOTE"
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError(
            "Phase 7W policy is invalid"
        )
    authority = raw["authority"]
    keys = {
        "network_enabled", "delivery_enabled", "retry_enabled", "escalation_enabled",
        "signature_enabled", "trusted_timestamp_enabled", "authenticated_recipient_enabled",
        "artifact_mutation_enabled", "artifact_deletion_enabled",
        "quarantine_enforcement_enabled", "approval_enabled", "efficacy_claims_enabled",
        "promotion_enabled", "scoring_enabled", "options_routing_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError(
            "Phase 7W authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


class ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.incident_registry = (
            ReviewedRangeCatalogIncidentNotificationExportIncidentRegistry(repository)
        )

    def materialize(
        self,
        incident_id: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig,
    ) -> tuple[
        ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent, ...
    ]:
        intents = tuple(
            self._from_event(event, config)
            for event in self.incident_registry.history(incident_id)
        )
        for intent in intents:
            self.persist(intent)
        return intents

    def persist(
        self,
        intent: ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent,
    ) -> bool:
        payload_hash = canonical_hash(intent)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO
               reviewed_range_catalog_incident_notification_export_incident_intents
               (notification_intent_id, incident_id, incident_event_id,
                notification_export_id, source_verification_id, occurred_at, event_type,
                incident_state, route, delivery_attempt_count, config_hash, payload_json,
                payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                intent.notification_intent_id, intent.incident_id, intent.incident_event_id,
                intent.notification_export_id, intent.source_verification_id,
                intent.occurred_at.isoformat(), intent.event_type.value,
                intent.incident_state.value, intent.route, intent.delivery_attempt_count,
                intent.config_hash, canonical_json(intent), payload_hash,
            ),
        )
        if not cursor.rowcount:
            if self._load(intent.notification_intent_id) != intent:
                raise ValueError("conflicting Phase 7W notification intent")
            return False
        self.repository.connection.commit()
        return True

    def load(
        self,
        incident_id: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig,
    ) -> tuple[
        ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent, ...
    ]:
        expected = tuple(
            self._from_event(event, config)
            for event in self.incident_registry.history(incident_id)
        )
        rows = self.repository.connection.execute(
            """SELECT notification_intent_id FROM
               reviewed_range_catalog_incident_notification_export_incident_intents
               WHERE incident_id = ? AND config_hash = ?
               ORDER BY occurred_at, notification_intent_id""",
            (incident_id, config.config_hash),
        ).fetchall()
        actual = tuple(self._load(str(row[0])) for row in rows)
        if actual != expected:
            raise ValueError("Phase 7W notification intent set is incomplete or corrupt")
        return actual

    def status(
        self,
        incident_id: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary:
        intents = self.load(incident_id, config)
        return ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary(
            incident_id, intents[0].notification_export_id, len(intents),
            tuple(intent.event_type for intent in intents), 0,
        )

    @staticmethod
    def _from_event(
        event: ReviewedRangeCatalogIncidentNotificationExportIncidentEvent,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent:
        return ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent(
            deterministic_id(
                "reviewed_range_catalog_incident_notification_export_incident_notification",
                (event.incident_event_id, config.config_hash),
            ),
            event.incident_id, event.incident_event_id, event.notification_export_id,
            event.source_verification_id, event.occurred_at, event.event_type,
            event.new_state, "LOCAL_OPERATOR_OUTBOX", 0, config.config_hash,
        )

    def _load(
        self, intent_id: str
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent:
        row = self.repository.connection.execute(
            """SELECT incident_id, incident_event_id, notification_export_id,
                      source_verification_id, occurred_at, event_type, incident_state,
                      route, delivery_attempt_count, config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_incident_notification_export_incident_intents
               WHERE notification_intent_id = ?""",
            (intent_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 7W notification intent")
        try:
            payload = json.loads(str(row[10]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7W notification intent is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[11]):
            raise ValueError("stored Phase 7W notification intent is corrupt")
        intent = _intent(payload)
        columns = (
            intent.incident_id, intent.incident_event_id, intent.notification_export_id,
            intent.source_verification_id, intent.occurred_at.isoformat(),
            intent.event_type.value, intent.incident_state.value, intent.route,
            intent.delivery_attempt_count, intent.config_hash,
        )
        if intent.notification_intent_id != intent_id or columns != tuple(row[:10]):
            raise ValueError("stored Phase 7W notification intent is corrupt")
        return intent


def _intent(
    payload: Mapping[str, object]
) -> ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent:
    cls = ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent
    required = set(cls.__dataclass_fields__) | {"__type__"}
    strings = (
        "notification_intent_id", "incident_id", "incident_event_id",
        "notification_export_id", "source_verification_id", "route", "config_hash",
        "notification_version",
    )
    false_fields = (
        "network_used", "delivery_attempted", "recipient_authenticated", "artifact_mutated",
        "quarantine_enforced", "approval_granted", "promotion_authority",
    )
    disclosures = payload.get("disclosures")
    if (
        set(payload) != required
        or payload.get("__type__") != cls.__name__
        or not all(isinstance(payload.get(key), str) for key in strings)
        or payload.get("delivery_attempt_count") != 0
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7W notification intent is corrupt")
    try:
        event_type = ReviewedRangeCatalogIncidentNotificationExportIncidentEventType(
            str(payload["event_type"])
        )
        state = ReviewedRangeCatalogIncidentNotificationExportIncidentState(
            str(payload["incident_state"])
        )
    except ValueError as error:
        raise ValueError("stored Phase 7W notification intent is corrupt") from error
    intent = cls(
        str(payload["notification_intent_id"]), str(payload["incident_id"]),
        str(payload["incident_event_id"]), str(payload["notification_export_id"]),
        str(payload["source_verification_id"]), _datetime(payload.get("occurred_at")),
        event_type, state, str(payload["route"]), 0, str(payload["config_hash"]),
        str(payload["notification_version"]), False, False, False, False, False, False, False,
        tuple(disclosures),
    )
    if intent.notification_intent_id != deterministic_id(
        "reviewed_range_catalog_incident_notification_export_incident_notification",
        (intent.incident_event_id, intent.config_hash),
    ):
        raise ValueError("stored Phase 7W notification intent is corrupt")
    return intent


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("stored Phase 7W notification intent is corrupt")
    raw = value["__datetime__"]
    if not isinstance(raw, str):
        raise ValueError("stored Phase 7W notification intent is corrupt")
    result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored Phase 7W notification intent is corrupt")
    return result
