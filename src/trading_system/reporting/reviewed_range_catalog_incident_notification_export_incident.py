"""Append-only Phase 7V incidents for failed Phase 7U verifications."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.reviewed_range_catalog_incident_notification_export_audit import (
    ReviewedRangeCatalogIncidentNotificationExportAuditRegistry,
    ReviewedRangeCatalogIncidentNotificationExportAuditStatus,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "CALLER_ASSERTED_TIME_IS_NOT_A_TRUSTED_TIMESTAMP",
    "ACTOR_ID_IS_UNAUTHENTICATED_CALLER_INPUT",
    "INCIDENT_STATE_DOES_NOT_MUTATE_DELETE_OR_QUARANTINE_THE_ARTIFACT",
    "INCIDENT_RESOLUTION_IS_NOT_DELIVERY_APPROVAL_OR_STRATEGY_PROMOTION",
    "NO_EFFICACY_SCORING_ALERTING_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError(ValueError):
    pass


class ReviewedRangeCatalogIncidentNotificationExportIncidentState(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class ReviewedRangeCatalogIncidentNotificationExportIncidentEventType(StrEnum):
    OPENED = "OPENED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportIncidentConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
    incident_event_id: str
    incident_id: str
    notification_export_id: str
    source_verification_id: str
    occurred_at: datetime
    event_type: ReviewedRangeCatalogIncidentNotificationExportIncidentEventType
    prior_state: ReviewedRangeCatalogIncidentNotificationExportIncidentState | None
    new_state: ReviewedRangeCatalogIncidentNotificationExportIncidentState
    actor_id: str
    note: str
    config_hash: str
    incident_version: str = "7V.1.0"
    trusted_timestamp: bool = False
    authenticated_actor: bool = False
    artifact_mutated: bool = False
    artifact_deleted: bool = False
    quarantine_enforced: bool = False
    notification_sent: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    disclosures: tuple[str, ...] = _DISCLOSURES

    def __post_init__(self) -> None:
        if (
            self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
            or not self.actor_id.strip()
            or len(self.actor_id) > 200
            or len(self.note) > 2000
            or self.incident_version != "7V.1.0"
            or self.trusted_timestamp
            or self.authenticated_actor
            or self.artifact_mutated
            or self.artifact_deleted
            or self.quarantine_enforced
            or self.notification_sent
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7V incident event is invalid")


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogIncidentNotificationExportIncidentSummary:
    incident_id: str
    notification_export_id: str
    state: ReviewedRangeCatalogIncidentNotificationExportIncidentState
    event_count: int
    opened_at: datetime
    latest_at: datetime
    failed_verification_id: str
    recovery_verification_id: str | None


def load_reviewed_range_catalog_incident_notification_export_incident_config(
    path: str | Path,
) -> ReviewedRangeCatalogIncidentNotificationExportIncidentConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "incident_version", "source", "opening_policy", "resolution_policy",
        "operator_identity", "timestamp", "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError(
            "Phase 7V configuration keys are invalid"
        )
    if (
        raw["incident_version"] != "7V.1.0"
        or raw["source"] != "PERSISTED_PHASE7U_VERIFICATION_RECEIPTS"
        or raw["opening_policy"] != "EXACT_FAILED_RECEIPT"
        or raw["resolution_policy"] != "EXPLICIT_LATER_VERIFIED_RECEIPT_REQUIRED"
        or raw["operator_identity"] != "CALLER_ASSERTED_UNAUTHENTICATED"
        or raw["timestamp"] != "CALLER_ASSERTED_UNTRUSTED_AWARE"
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError(
            "Phase 7V policy is invalid"
        )
    authority = raw["authority"]
    authority_keys = {
        "network_enabled", "notification_enabled", "signature_enabled",
        "trusted_timestamp_enabled", "authenticated_identity_enabled",
        "artifact_mutation_enabled", "artifact_deletion_enabled",
        "quarantine_enforcement_enabled", "approval_enabled", "efficacy_claims_enabled",
        "promotion_enabled", "scoring_enabled", "alerts_enabled", "options_routing_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != authority_keys or any(
        value is not False for value in authority.values()
    ):
        raise ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError(
            "Phase 7V authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogIncidentNotificationExportIncidentConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


class ReviewedRangeCatalogIncidentNotificationExportIncidentRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.audit_registry = ReviewedRangeCatalogIncidentNotificationExportAuditRegistry(
            repository
        )

    def open(
        self, *, verification_id: str, occurred_at: datetime, actor_id: str, note: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
        failure = self.audit_registry.load(verification_id)
        if failure.status is not ReviewedRangeCatalogIncidentNotificationExportAuditStatus.FAILED:
            raise ValueError("Phase 7V incident requires a failed Phase 7U receipt")
        self._check_time(occurred_at, failure.verified_at)
        incident_id = deterministic_id(
            "reviewed_range_catalog_incident_notification_export_incident",
            (failure.notification_export_id, failure.verification_id),
        )
        event = self._build(
            incident_id, failure.notification_export_id, failure.verification_id, occurred_at,
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.OPENED, None,
            ReviewedRangeCatalogIncidentNotificationExportIncidentState.OPEN, actor_id, note,
            config,
        )
        self.persist(event)
        return event

    def acknowledge(
        self, *, incident_id: str, occurred_at: datetime, actor_id: str, note: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
        history = self.history(incident_id)
        opened = history[0]
        event = self._build(
            incident_id, opened.notification_export_id, opened.source_verification_id,
            occurred_at,
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.ACKNOWLEDGED,
            ReviewedRangeCatalogIncidentNotificationExportIncidentState.OPEN,
            ReviewedRangeCatalogIncidentNotificationExportIncidentState.ACKNOWLEDGED,
            actor_id, note, config,
        )
        existing = self._existing(event.incident_event_id)
        if existing is not None:
            return existing
        if (
            history[-1].new_state
            is not ReviewedRangeCatalogIncidentNotificationExportIncidentState.OPEN
        ):
            raise ValueError("Phase 7V incident is not open")
        self._check_time(occurred_at, history[-1].occurred_at)
        self.persist(event)
        return event

    def resolve(
        self, *, incident_id: str, recovery_verification_id: str, occurred_at: datetime,
        actor_id: str, note: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
        history = self.history(incident_id)
        opened = history[0]
        failure = self.audit_registry.load(opened.source_verification_id)
        recovery = self.audit_registry.load(recovery_verification_id)
        if (
            recovery.status
            is not ReviewedRangeCatalogIncidentNotificationExportAuditStatus.VERIFIED
            or recovery.notification_export_id != opened.notification_export_id
            or recovery.verified_at <= failure.verified_at
        ):
            raise ValueError(
                "Phase 7V resolution requires a later verified receipt for the same export"
            )
        prior = history[-1].new_state
        if prior is ReviewedRangeCatalogIncidentNotificationExportIncidentState.RESOLVED:
            latest = history[-1]
            expected = self._build(
                incident_id, opened.notification_export_id, recovery.verification_id,
                occurred_at,
                ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.RESOLVED,
                latest.prior_state,
                ReviewedRangeCatalogIncidentNotificationExportIncidentState.RESOLVED,
                actor_id, note, config,
            )
            if latest == expected:
                return latest
            raise ValueError("Phase 7V incident is already resolved")
        event = self._build(
            incident_id, opened.notification_export_id, recovery.verification_id, occurred_at,
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.RESOLVED, prior,
            ReviewedRangeCatalogIncidentNotificationExportIncidentState.RESOLVED, actor_id, note,
            config,
        )
        existing = self._existing(event.incident_event_id)
        if existing is not None:
            return existing
        self._check_time(occurred_at, max(history[-1].occurred_at, recovery.verified_at))
        self.persist(event)
        return event

    def persist(self, event: ReviewedRangeCatalogIncidentNotificationExportIncidentEvent) -> bool:
        payload_hash = canonical_hash(event)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO
               reviewed_range_catalog_incident_notification_export_incident_events
               (incident_event_id, incident_id, notification_export_id,
                source_verification_id, occurred_at, event_type, prior_state, new_state,
                actor_id, note, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.incident_event_id, event.incident_id, event.notification_export_id,
                event.source_verification_id, event.occurred_at.isoformat(),
                event.event_type.value,
                None if event.prior_state is None else event.prior_state.value,
                event.new_state.value, event.actor_id, event.note, event.config_hash,
                canonical_json(event), payload_hash,
            ),
        )
        if not cursor.rowcount:
            if self._existing(event.incident_event_id) != event:
                raise ValueError("conflicting Phase 7V incident event")
            return False
        self.repository.connection.commit()
        return True

    def history(
        self, incident_id: str
    ) -> tuple[ReviewedRangeCatalogIncidentNotificationExportIncidentEvent, ...]:
        rows = self.repository.connection.execute(
            """SELECT incident_event_id, notification_export_id, source_verification_id,
                      occurred_at, event_type, prior_state, new_state, actor_id, note,
                      config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_incident_notification_export_incident_events
               WHERE incident_id = ? ORDER BY occurred_at, incident_event_id""",
            (incident_id,),
        ).fetchall()
        if not rows:
            raise ValueError("unknown Phase 7V incident")
        events = tuple(self._from_row(incident_id, row) for row in rows)
        self._validate_history(events)
        failure = self.audit_registry.load(events[0].source_verification_id)
        expected_id = deterministic_id(
            "reviewed_range_catalog_incident_notification_export_incident",
            (failure.notification_export_id, failure.verification_id),
        )
        if (
            failure.status is not ReviewedRangeCatalogIncidentNotificationExportAuditStatus.FAILED
            or failure.notification_export_id != events[0].notification_export_id
            or expected_id != incident_id
        ):
            raise ValueError("stored Phase 7V incident history is corrupt")
        for event in events[1:]:
            source = self.audit_registry.load(event.source_verification_id)
            valid = (
                source.verification_id == failure.verification_id
                if event.event_type
                is ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.ACKNOWLEDGED
                else source.status
                is ReviewedRangeCatalogIncidentNotificationExportAuditStatus.VERIFIED
                and source.notification_export_id == failure.notification_export_id
                and source.verified_at > failure.verified_at
                and event.occurred_at >= source.verified_at
            )
            if not valid:
                raise ValueError("stored Phase 7V incident history is corrupt")
        return events

    def status(
        self, incident_id: str
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentSummary:
        events = self.history(incident_id)
        opened, latest = events[0], events[-1]
        recovery = (
            latest.source_verification_id
            if latest.event_type
            is ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.RESOLVED
            else None
        )
        return ReviewedRangeCatalogIncidentNotificationExportIncidentSummary(
            incident_id, opened.notification_export_id, latest.new_state, len(events),
            opened.occurred_at, latest.occurred_at, opened.source_verification_id, recovery,
        )

    def _build(
        self, incident_id: str, export_id: str, verification_id: str, occurred_at: datetime,
        event_type: ReviewedRangeCatalogIncidentNotificationExportIncidentEventType,
        prior_state: ReviewedRangeCatalogIncidentNotificationExportIncidentState | None,
        new_state: ReviewedRangeCatalogIncidentNotificationExportIncidentState,
        actor_id: str, note: str,
        config: ReviewedRangeCatalogIncidentNotificationExportIncidentConfig,
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
        identity = (
            incident_id, export_id, verification_id, occurred_at, event_type, prior_state,
            new_state, actor_id, note, config.config_hash,
        )
        return ReviewedRangeCatalogIncidentNotificationExportIncidentEvent(
            deterministic_id(
                "reviewed_range_catalog_incident_notification_export_incident_event", identity
            ),
            incident_id, export_id, verification_id, occurred_at, event_type, prior_state,
            new_state, actor_id, note, config.config_hash,
        )

    def _existing(
        self, event_id: str
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent | None:
        row = self.repository.connection.execute(
            """SELECT incident_id, notification_export_id, source_verification_id,
                      occurred_at, event_type, prior_state, new_state, actor_id, note,
                      config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_incident_notification_export_incident_events
               WHERE incident_event_id = ?""",
            (event_id,),
        ).fetchone()
        return None if row is None else self._from_row(str(row[0]), (event_id, *row[1:]))

    def _from_row(
        self, incident_id: str, row: tuple[object, ...]
    ) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
        try:
            payload = json.loads(str(row[10]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7V incident event is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[11]):
            raise ValueError("stored Phase 7V incident event is corrupt")
        event = _event(payload)
        columns = (
            event.incident_event_id, event.notification_export_id,
            event.source_verification_id, event.occurred_at.isoformat(),
            event.event_type.value,
            None if event.prior_state is None else event.prior_state.value,
            event.new_state.value, event.actor_id, event.note, event.config_hash,
        )
        if event.incident_id != incident_id or columns != tuple(row[:10]):
            raise ValueError("stored Phase 7V incident event is corrupt")
        return event

    @staticmethod
    def _validate_history(
        events: tuple[ReviewedRangeCatalogIncidentNotificationExportIncidentEvent, ...]
    ) -> None:
        first = events[0]
        state = ReviewedRangeCatalogIncidentNotificationExportIncidentState
        kind = ReviewedRangeCatalogIncidentNotificationExportIncidentEventType
        if (
            first.event_type is not kind.OPENED
            or first.prior_state is not None
            or first.new_state is not state.OPEN
        ):
            raise ValueError("stored Phase 7V incident history is corrupt")
        previous = first
        for event in events[1:]:
            valid = (
                event.prior_state is previous.new_state
                and event.occurred_at >= previous.occurred_at
                and event.notification_export_id == first.notification_export_id
                and ((event.event_type is kind.ACKNOWLEDGED and previous.new_state is state.OPEN
                      and event.new_state is state.ACKNOWLEDGED)
                     or (event.event_type is kind.RESOLVED
                         and previous.new_state in {state.OPEN, state.ACKNOWLEDGED}
                         and event.new_state is state.RESOLVED))
            )
            if not valid:
                raise ValueError("stored Phase 7V incident history is corrupt")
            previous = event

    @staticmethod
    def _check_time(actual: datetime, minimum: datetime) -> None:
        if actual.tzinfo is None or actual.utcoffset() is None or actual < minimum:
            raise ValueError("Phase 7V event time is invalid")


def _event(
    payload: Mapping[str, object]
) -> ReviewedRangeCatalogIncidentNotificationExportIncidentEvent:
    required = {
        field
        for field in (
            ReviewedRangeCatalogIncidentNotificationExportIncidentEvent.__dataclass_fields__
        )
    } | {"__type__"}
    strings = (
        "incident_event_id", "incident_id", "notification_export_id",
        "source_verification_id", "actor_id", "note", "config_hash", "incident_version",
    )
    false_fields = (
        "trusted_timestamp", "authenticated_actor", "artifact_mutated", "artifact_deleted",
        "quarantine_enforced", "notification_sent", "approval_granted", "promotion_authority",
    )
    disclosures = payload.get("disclosures")
    if (
        set(payload) != required
        or payload.get("__type__")
        != "ReviewedRangeCatalogIncidentNotificationExportIncidentEvent"
        or not all(isinstance(payload.get(key), str) for key in strings)
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7V incident event is corrupt")
    try:
        prior_raw = payload.get("prior_state")
        prior = (
            None if prior_raw is None
            else ReviewedRangeCatalogIncidentNotificationExportIncidentState(str(prior_raw))
        )
        event_type = ReviewedRangeCatalogIncidentNotificationExportIncidentEventType(
            str(payload["event_type"])
        )
        new_state = ReviewedRangeCatalogIncidentNotificationExportIncidentState(
            str(payload["new_state"])
        )
    except ValueError as error:
        raise ValueError("stored Phase 7V incident event is corrupt") from error
    event = ReviewedRangeCatalogIncidentNotificationExportIncidentEvent(
        str(payload["incident_event_id"]), str(payload["incident_id"]),
        str(payload["notification_export_id"]), str(payload["source_verification_id"]),
        _datetime(payload.get("occurred_at")), event_type, prior, new_state,
        str(payload["actor_id"]), str(payload["note"]), str(payload["config_hash"]),
        str(payload["incident_version"]), False, False, False, False, False, False, False, False,
        tuple(disclosures),
    )
    identity = (
        event.incident_id, event.notification_export_id, event.source_verification_id,
        event.occurred_at, event.event_type, event.prior_state, event.new_state,
        event.actor_id, event.note, event.config_hash,
    )
    if event.incident_event_id != deterministic_id(
        "reviewed_range_catalog_incident_notification_export_incident_event", identity
    ):
        raise ValueError("stored Phase 7V incident event is corrupt")
    return event


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("stored Phase 7V incident event is corrupt")
    raw = value["__datetime__"]
    if not isinstance(raw, str):
        raise ValueError("stored Phase 7V incident event is corrupt")
    result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored Phase 7V incident event is corrupt")
    return result
