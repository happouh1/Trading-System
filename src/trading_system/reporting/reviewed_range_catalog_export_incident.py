"""Append-only Phase 7R incident history for failed Phase 7Q verifications."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.persistence import SQLiteRepository
from trading_system.reporting.reviewed_range_catalog_export_audit import (
    ReviewedRangeCatalogExportAuditRegistry,
    ReviewedRangeCatalogExportAuditStatus,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DISCLOSURES = (
    "CALLER_ASSERTED_TIME_IS_NOT_A_TRUSTED_TIMESTAMP",
    "ACTOR_ID_IS_UNAUTHENTICATED_CALLER_INPUT",
    "INCIDENT_STATE_DOES_NOT_MUTATE_OR_DELETE_THE_ARTIFACT",
    "INCIDENT_RESOLUTION_IS_NOT_APPROVAL_OR_STRATEGY_PROMOTION",
    "NO_EFFICACY_SCORING_ALERTING_OR_TRADING_AUTHORITY",
)


class ReviewedRangeCatalogExportIncidentConfigError(ValueError):
    pass


class ReviewedRangeCatalogExportIncidentState(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class ReviewedRangeCatalogExportIncidentEventType(StrEnum):
    OPENED = "OPENED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportIncidentConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportIncidentEvent:
    incident_event_id: str
    incident_id: str
    catalog_export_id: str
    source_verification_id: str
    occurred_at: datetime
    event_type: ReviewedRangeCatalogExportIncidentEventType
    prior_state: ReviewedRangeCatalogExportIncidentState | None
    new_state: ReviewedRangeCatalogExportIncidentState
    actor_id: str
    note: str
    config_hash: str
    incident_version: str = "7R.1.0"
    trusted_timestamp: bool = False
    authenticated_actor: bool = False
    artifact_mutated: bool = False
    quarantine_enforced: bool = False
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
            or self.incident_version != "7R.1.0"
            or self.trusted_timestamp
            or self.authenticated_actor
            or self.artifact_mutated
            or self.quarantine_enforced
            or self.approval_granted
            or self.promotion_authority
            or self.disclosures != _DISCLOSURES
        ):
            raise ValueError("Phase 7R incident event is invalid")


@dataclass(frozen=True, slots=True)
class ReviewedRangeCatalogExportIncidentSummary:
    incident_id: str
    catalog_export_id: str
    state: ReviewedRangeCatalogExportIncidentState
    event_count: int
    opened_at: datetime
    latest_at: datetime
    failed_verification_id: str
    recovery_verification_id: str | None


def load_reviewed_range_catalog_export_incident_config(
    path: str | Path,
) -> ReviewedRangeCatalogExportIncidentConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "incident_version", "source", "opening_policy", "resolution_policy",
        "operator_identity", "timestamp", "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ReviewedRangeCatalogExportIncidentConfigError(
            "Phase 7R configuration keys are invalid"
        )
    if (
        raw["incident_version"] != "7R.1.0"
        or raw["source"] != "PERSISTED_PHASE7Q_VERIFICATION_RECEIPTS"
        or raw["opening_policy"] != "EXACT_FAILED_RECEIPT"
        or raw["resolution_policy"] != "EXPLICIT_LATER_VERIFIED_RECEIPT_REQUIRED"
        or raw["operator_identity"] != "CALLER_ASSERTED_UNAUTHENTICATED"
        or raw["timestamp"] != "CALLER_ASSERTED_UNTRUSTED_AWARE"
    ):
        raise ReviewedRangeCatalogExportIncidentConfigError("Phase 7R policy is invalid")
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
        raise ReviewedRangeCatalogExportIncidentConfigError(
            "Phase 7R authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return ReviewedRangeCatalogExportIncidentConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


class ReviewedRangeCatalogExportIncidentRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository
        self.audit_registry = ReviewedRangeCatalogExportAuditRegistry(repository)

    def open(
        self, *, verification_id: str, occurred_at: datetime, actor_id: str, note: str,
        config: ReviewedRangeCatalogExportIncidentConfig,
    ) -> ReviewedRangeCatalogExportIncidentEvent:
        failure = self.audit_registry.load(verification_id)
        if failure.status is not ReviewedRangeCatalogExportAuditStatus.FAILED:
            raise ValueError("Phase 7R incident requires a failed Phase 7Q receipt")
        if occurred_at < failure.verified_at:
            raise ValueError("Phase 7R incident cannot predate its failed verification")
        incident_id = deterministic_id(
            "reviewed_range_catalog_export_incident",
            (failure.catalog_export_id, failure.verification_id),
        )
        event = self._build_event(
            incident_id=incident_id,
            export_id=failure.catalog_export_id,
            verification_id=failure.verification_id,
            occurred_at=occurred_at,
            event_type=ReviewedRangeCatalogExportIncidentEventType.OPENED,
            prior_state=None,
            new_state=ReviewedRangeCatalogExportIncidentState.OPEN,
            actor_id=actor_id,
            note=note,
            config=config,
        )
        self.persist(event)
        return event

    def acknowledge(
        self, *, incident_id: str, occurred_at: datetime, actor_id: str, note: str,
        config: ReviewedRangeCatalogExportIncidentConfig,
    ) -> ReviewedRangeCatalogExportIncidentEvent:
        history = self.history(incident_id)
        opened = history[0]
        event = self._build_event(
            incident_id=incident_id,
            export_id=opened.catalog_export_id,
            verification_id=opened.source_verification_id,
            occurred_at=occurred_at,
            event_type=ReviewedRangeCatalogExportIncidentEventType.ACKNOWLEDGED,
            prior_state=ReviewedRangeCatalogExportIncidentState.OPEN,
            new_state=ReviewedRangeCatalogExportIncidentState.ACKNOWLEDGED,
            actor_id=actor_id,
            note=note,
            config=config,
        )
        existing = self._existing(event.incident_event_id)
        if existing is not None:
            return existing
        if history[-1].new_state is not ReviewedRangeCatalogExportIncidentState.OPEN:
            raise ValueError("Phase 7R incident is not open")
        self._check_time(occurred_at, history[-1].occurred_at)
        self.persist(event)
        return event

    def resolve(
        self, *, incident_id: str, recovery_verification_id: str, occurred_at: datetime,
        actor_id: str, note: str, config: ReviewedRangeCatalogExportIncidentConfig,
    ) -> ReviewedRangeCatalogExportIncidentEvent:
        history = self.history(incident_id)
        opened = history[0]
        recovery = self.audit_registry.load(recovery_verification_id)
        if (
            recovery.status is not ReviewedRangeCatalogExportAuditStatus.VERIFIED
            or recovery.catalog_export_id != opened.catalog_export_id
        ):
            raise ValueError("Phase 7R resolution requires a verified receipt for the same export")
        failure = self.audit_registry.load(opened.source_verification_id)
        if recovery.verified_at <= failure.verified_at:
            raise ValueError("Phase 7R recovery verification must follow the failure")
        prior_state = history[-1].new_state
        if prior_state is ReviewedRangeCatalogExportIncidentState.RESOLVED:
            latest = history[-1]
            expected = self._build_event(
                incident_id=incident_id,
                export_id=opened.catalog_export_id,
                verification_id=recovery.verification_id,
                occurred_at=occurred_at,
                event_type=ReviewedRangeCatalogExportIncidentEventType.RESOLVED,
                prior_state=latest.prior_state,
                new_state=ReviewedRangeCatalogExportIncidentState.RESOLVED,
                actor_id=actor_id,
                note=note,
                config=config,
            )
            if latest == expected:
                return latest
            raise ValueError("Phase 7R incident is already resolved")
        event = self._build_event(
            incident_id=incident_id,
            export_id=opened.catalog_export_id,
            verification_id=recovery.verification_id,
            occurred_at=occurred_at,
            event_type=ReviewedRangeCatalogExportIncidentEventType.RESOLVED,
            prior_state=prior_state,
            new_state=ReviewedRangeCatalogExportIncidentState.RESOLVED,
            actor_id=actor_id,
            note=note,
            config=config,
        )
        existing = self._existing(event.incident_event_id)
        if existing is not None:
            return existing
        if prior_state not in {
            ReviewedRangeCatalogExportIncidentState.OPEN,
            ReviewedRangeCatalogExportIncidentState.ACKNOWLEDGED,
        }:
            raise ValueError("Phase 7R incident is already resolved")
        self._check_time(occurred_at, max(history[-1].occurred_at, recovery.verified_at))
        self.persist(event)
        return event

    def persist(self, event: ReviewedRangeCatalogExportIncidentEvent) -> bool:
        payload_hash = canonical_hash(event)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO reviewed_range_catalog_export_incident_events
               (incident_event_id, incident_id, catalog_export_id, source_verification_id,
                occurred_at, event_type, prior_state, new_state, actor_id, note, config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.incident_event_id, event.incident_id, event.catalog_export_id,
                event.source_verification_id, event.occurred_at.isoformat(),
                event.event_type.value,
                None if event.prior_state is None else event.prior_state.value,
                event.new_state.value, event.actor_id, event.note, event.config_hash,
                canonical_json(event), payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self._existing(event.incident_event_id)
            if stored != event:
                raise ValueError("conflicting Phase 7R incident event")
            return False
        self.repository.connection.commit()
        return True

    def history(self, incident_id: str) -> tuple[ReviewedRangeCatalogExportIncidentEvent, ...]:
        rows = self.repository.connection.execute(
            """SELECT incident_event_id, catalog_export_id, source_verification_id,
                      occurred_at, event_type, prior_state, new_state, actor_id, note,
                      config_hash, payload_json, payload_hash
               FROM reviewed_range_catalog_export_incident_events
               WHERE incident_id = ? ORDER BY occurred_at, incident_event_id""",
            (incident_id,),
        ).fetchall()
        if not rows:
            raise ValueError("unknown Phase 7R incident")
        events = tuple(self._event_from_row(incident_id, row) for row in rows)
        self._validate_history(events)
        failure = self.audit_registry.load(events[0].source_verification_id)
        expected_incident_id = deterministic_id(
            "reviewed_range_catalog_export_incident",
            (failure.catalog_export_id, failure.verification_id),
        )
        if (
            failure.status is not ReviewedRangeCatalogExportAuditStatus.FAILED
            or failure.catalog_export_id != events[0].catalog_export_id
            or incident_id != expected_incident_id
        ):
            raise ValueError("stored Phase 7R incident history is corrupt")
        for event in events[1:]:
            source = self.audit_registry.load(event.source_verification_id)
            if event.event_type is ReviewedRangeCatalogExportIncidentEventType.ACKNOWLEDGED:
                valid_source = source.verification_id == failure.verification_id
            else:
                valid_source = (
                    source.status is ReviewedRangeCatalogExportAuditStatus.VERIFIED
                    and source.catalog_export_id == failure.catalog_export_id
                    and source.verified_at > failure.verified_at
                    and event.occurred_at >= source.verified_at
                )
            if not valid_source:
                raise ValueError("stored Phase 7R incident history is corrupt")
        return events

    def status(self, incident_id: str) -> ReviewedRangeCatalogExportIncidentSummary:
        events = self.history(incident_id)
        opened = events[0]
        latest = events[-1]
        recovery = (
            latest.source_verification_id
            if latest.event_type is ReviewedRangeCatalogExportIncidentEventType.RESOLVED
            else None
        )
        return ReviewedRangeCatalogExportIncidentSummary(
            incident_id, opened.catalog_export_id, latest.new_state, len(events),
            opened.occurred_at, latest.occurred_at, opened.source_verification_id, recovery,
        )

    def _build_event(
        self, *, incident_id: str, export_id: str, verification_id: str,
        occurred_at: datetime, event_type: ReviewedRangeCatalogExportIncidentEventType,
        prior_state: ReviewedRangeCatalogExportIncidentState | None,
        new_state: ReviewedRangeCatalogExportIncidentState, actor_id: str, note: str,
        config: ReviewedRangeCatalogExportIncidentConfig,
    ) -> ReviewedRangeCatalogExportIncidentEvent:
        identity = (
            incident_id, export_id, verification_id, occurred_at, event_type, prior_state,
            new_state, actor_id, note, config.config_hash,
        )
        return ReviewedRangeCatalogExportIncidentEvent(
            deterministic_id("reviewed_range_catalog_export_incident_event", identity),
            incident_id, export_id, verification_id, occurred_at, event_type, prior_state,
            new_state, actor_id, note, config.config_hash,
        )

    def _existing(self, event_id: str) -> ReviewedRangeCatalogExportIncidentEvent | None:
        row = self.repository.connection.execute(
            """SELECT incident_id, catalog_export_id, source_verification_id, occurred_at,
                      event_type, prior_state, new_state, actor_id, note, config_hash,
                      payload_json, payload_hash
               FROM reviewed_range_catalog_export_incident_events
               WHERE incident_event_id = ?""",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return self._event_from_row(str(row[0]), (event_id, *row[1:]))

    def _event_from_row(
        self, incident_id: str, row: tuple[object, ...]
    ) -> ReviewedRangeCatalogExportIncidentEvent:
        try:
            payload = json.loads(str(row[10]))
        except json.JSONDecodeError as error:
            raise ValueError("stored Phase 7R incident event is corrupt") from error
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[11]):
            raise ValueError("stored Phase 7R incident event is corrupt")
        event = _incident_event(payload)
        columns = (
            event.incident_event_id, event.catalog_export_id, event.source_verification_id,
            event.occurred_at.isoformat(), event.event_type.value,
            None if event.prior_state is None else event.prior_state.value,
            event.new_state.value, event.actor_id, event.note, event.config_hash,
        )
        if event.incident_id != incident_id or columns != tuple(row[:10]):
            raise ValueError("stored Phase 7R incident event is corrupt")
        return event

    @staticmethod
    def _validate_history(events: tuple[ReviewedRangeCatalogExportIncidentEvent, ...]) -> None:
        first = events[0]
        if (
            first.event_type is not ReviewedRangeCatalogExportIncidentEventType.OPENED
            or first.prior_state is not None
            or first.new_state is not ReviewedRangeCatalogExportIncidentState.OPEN
        ):
            raise ValueError("stored Phase 7R incident history is corrupt")
        previous = first
        for event in events[1:]:
            valid_transition = (
                event.prior_state is previous.new_state
                and event.occurred_at >= previous.occurred_at
                and event.catalog_export_id == first.catalog_export_id
                and (
                    (
                        event.event_type
                        is ReviewedRangeCatalogExportIncidentEventType.ACKNOWLEDGED
                        and previous.new_state is ReviewedRangeCatalogExportIncidentState.OPEN
                        and event.new_state
                        is ReviewedRangeCatalogExportIncidentState.ACKNOWLEDGED
                    )
                    or (
                        event.event_type
                        is ReviewedRangeCatalogExportIncidentEventType.RESOLVED
                        and previous.new_state in {
                            ReviewedRangeCatalogExportIncidentState.OPEN,
                            ReviewedRangeCatalogExportIncidentState.ACKNOWLEDGED,
                        }
                        and event.new_state is ReviewedRangeCatalogExportIncidentState.RESOLVED
                    )
                )
            )
            if not valid_transition:
                raise ValueError("stored Phase 7R incident history is corrupt")
            previous = event

    @staticmethod
    def _check_time(actual: datetime, minimum: datetime) -> None:
        if actual.tzinfo is None or actual.utcoffset() is None or actual < minimum:
            raise ValueError("Phase 7R event time is invalid")


def _incident_event(payload: Mapping[str, object]) -> ReviewedRangeCatalogExportIncidentEvent:
    required = {
        field for field in ReviewedRangeCatalogExportIncidentEvent.__dataclass_fields__
    } | {"__type__"}
    strings = (
        "incident_event_id", "incident_id", "catalog_export_id", "source_verification_id",
        "actor_id", "note", "config_hash", "incident_version",
    )
    false_fields = (
        "trusted_timestamp", "authenticated_actor", "artifact_mutated",
        "quarantine_enforced", "approval_granted", "promotion_authority",
    )
    disclosures = payload.get("disclosures")
    if (
        set(payload) != required
        or payload.get("__type__") != "ReviewedRangeCatalogExportIncidentEvent"
        or not all(isinstance(payload.get(key), str) for key in strings)
        or not isinstance(disclosures, list)
        or not all(isinstance(item, str) for item in disclosures)
        or any(payload.get(key) is not False for key in false_fields)
    ):
        raise ValueError("stored Phase 7R incident event is corrupt")
    prior_raw = payload.get("prior_state")
    try:
        prior = (
            None if prior_raw is None else ReviewedRangeCatalogExportIncidentState(str(prior_raw))
        )
        event_type = ReviewedRangeCatalogExportIncidentEventType(str(payload["event_type"]))
        new_state = ReviewedRangeCatalogExportIncidentState(str(payload["new_state"]))
    except ValueError as error:
        raise ValueError("stored Phase 7R incident event is corrupt") from error
    event = ReviewedRangeCatalogExportIncidentEvent(
        str(payload["incident_event_id"]), str(payload["incident_id"]),
        str(payload["catalog_export_id"]), str(payload["source_verification_id"]),
        _canonical_datetime(payload.get("occurred_at")), event_type, prior, new_state,
        str(payload["actor_id"]), str(payload["note"]), str(payload["config_hash"]),
        str(payload["incident_version"]), False, False, False, False, False, False,
        tuple(disclosures),
    )
    identity = (
        event.incident_id, event.catalog_export_id, event.source_verification_id,
        event.occurred_at, event.event_type, event.prior_state, event.new_state,
        event.actor_id, event.note, event.config_hash,
    )
    if event.incident_event_id != deterministic_id(
        "reviewed_range_catalog_export_incident_event", identity
    ):
        raise ValueError("stored Phase 7R incident event is corrupt")
    return event


def _canonical_datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("stored Phase 7R incident event is corrupt")
    timestamp = value["__datetime__"]
    if not isinstance(timestamp, str):
        raise ValueError("stored Phase 7R incident event is corrupt")
    result = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("stored Phase 7R incident event is corrupt")
    return result
