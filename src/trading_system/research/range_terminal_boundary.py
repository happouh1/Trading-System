"""Terminal offline authority boundary for the completed Phase 7 research chain."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.reporting import (
    ReviewedRangeCatalogIncidentNotificationExportIncidentEventType,
    ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary,
)
from trading_system.serialization import canonical_hash, deterministic_id

_TERMINAL_POLICY = "NO_DOWNSTREAM_EXPORT_VERIFICATION_INCIDENT_OR_DELIVERY_CHAIN"
_ALLOWED_ROUTE = "LOCAL_OPERATOR_OUTBOX"


class RangeTerminalBoundaryConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeTerminalBoundaryConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeTerminalBoundaryAssessment:
    assessment_id: str
    incident_id: str
    notification_export_id: str
    intent_count: int
    event_types: tuple[
        ReviewedRangeCatalogIncidentNotificationExportIncidentEventType, ...
    ]
    route: str
    delivery_attempt_count: int
    config_hash: str
    boundary_version: str = "7X.1.0"
    terminal_boundary: bool = True
    network_used: bool = False
    delivery_attempted: bool = False
    artifact_exported: bool = False
    incident_created: bool = False
    approval_granted: bool = False
    promotion_authority: bool = False
    broker_write_performed: bool = False

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.incident_id
            or not self.notification_export_id
            or self.intent_count <= 0
            or len(self.event_types) != self.intent_count
            or self.route != _ALLOWED_ROUTE
            or self.delivery_attempt_count != 0
            or self.boundary_version != "7X.1.0"
            or not self.terminal_boundary
            or self.network_used
            or self.delivery_attempted
            or self.artifact_exported
            or self.incident_created
            or self.approval_granted
            or self.promotion_authority
            or self.broker_write_performed
        ):
            raise ValueError("Phase 7X terminal-boundary assessment is invalid")


def load_range_terminal_boundary_config(
    path: str | Path,
) -> RangeTerminalBoundaryConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "boundary_version",
        "source",
        "terminal_policy",
        "allowed_route",
        "authority",
    }:
        raise RangeTerminalBoundaryConfigError("Phase 7X configuration keys are invalid")
    if (
        raw["boundary_version"] != "7X.1.0"
        or raw["source"] != "VALIDATED_PHASE7W_LOCAL_INTENTS"
        or raw["terminal_policy"] != _TERMINAL_POLICY
        or raw["allowed_route"] != _ALLOWED_ROUTE
    ):
        raise RangeTerminalBoundaryConfigError("Phase 7X terminal policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "network_enabled",
        "delivery_enabled",
        "retry_enabled",
        "escalation_enabled",
        "credential_access_enabled",
        "recipient_resolution_enabled",
        "artifact_export_enabled",
        "incident_creation_enabled",
        "quarantine_enforcement_enabled",
        "approval_enabled",
        "efficacy_claims_enabled",
        "promotion_enabled",
        "scoring_enabled",
        "options_routing_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != expected_authority or any(
        value is not False for value in authority.values()
    ):
        raise RangeTerminalBoundaryConfigError("Phase 7X authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeTerminalBoundaryConfig(MappingProxyType(frozen), canonical_hash(raw))


def assess_range_terminal_boundary(
    config: RangeTerminalBoundaryConfig,
    summary: ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary,
) -> RangeTerminalBoundaryAssessment:
    if summary.intent_count <= 0 or len(summary.event_types) != summary.intent_count:
        raise ValueError("Phase 7W source intent set is empty or incomplete")
    if summary.delivery_attempt_count != 0:
        raise ValueError("Phase 7W source crossed the offline delivery boundary")
    identity = (
        summary.incident_id,
        summary.notification_export_id,
        summary.intent_count,
        summary.event_types,
        config.config_hash,
        "7X.1.0",
    )
    return RangeTerminalBoundaryAssessment(
        deterministic_id("range_terminal_boundary_assessment", identity),
        summary.incident_id,
        summary.notification_export_id,
        summary.intent_count,
        summary.event_types,
        _ALLOWED_ROUTE,
        summary.delivery_attempt_count,
        config.config_hash,
    )
