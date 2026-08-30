"""Immutable Phase 5D operator-control and incident events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from trading_system.operations.control_config import OperationsControlConfig
from trading_system.operations.runner import JobRunRequest
from trading_system.serialization import deterministic_id

_COMPONENTS = {
    "CORE_RESEARCH",
    "RESEARCH_EVALUATION",
    "MODELING",
    "PAPER",
    "WEBULL_SANDBOX",
    "PORTFOLIO",
    "OPTIONS",
}


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _reasons(value: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(sorted(set(value)))
    if not result or any(not item for item in result):
        raise ValueError("control reasons must be nonempty")
    return result


class ApprovalAction(StrEnum):
    GRANT = "GRANT"
    REVOKE = "REVOKE"


class SwitchAction(StrEnum):
    ENGAGE = "ENGAGE"
    RELEASE = "RELEASE"


class CancellationAction(StrEnum):
    REQUEST = "REQUEST"
    CLEAR = "CLEAR"


class IncidentAction(StrEnum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    RESOLVE = "RESOLVE"
    REOPEN = "REOPEN"


class IncidentState(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class ControlStatus(StrEnum):
    HALTED = "HALTED"
    ATTENTION = "ATTENTION"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class ApprovalEvent:
    event_id: str
    request_id: str
    operator_id: str
    action: ApprovalAction
    known_at: datetime
    expires_at: datetime | None
    reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "approval known_at")
        if not all((self.event_id, self.request_id, self.operator_id, self.config_hash)):
            raise ValueError("approval identity is required")
        if self.reasons != _reasons(self.reasons):
            raise ValueError("approval reasons must be canonical")
        if self.action is ApprovalAction.GRANT:
            if self.expires_at is None:
                raise ValueError("approval grant requires expiration")
            _aware(self.expires_at, "approval expires_at")
            if self.expires_at <= self.known_at:
                raise ValueError("approval expiration must follow grant")
        elif self.expires_at is not None:
            raise ValueError("approval revocation cannot have expiration")

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        operator_id: str,
        action: ApprovalAction,
        known_at: datetime,
        expires_at: datetime | None,
        reasons: tuple[str, ...],
        config: OperationsControlConfig,
    ) -> ApprovalEvent:
        canonical_reasons = _reasons(reasons)
        if expires_at is not None and (
            expires_at - known_at
        ).total_seconds() > config.maximum_approval_lifetime_seconds:
            raise ValueError("approval lifetime exceeds configured maximum")
        identity = (request_id, operator_id, action, known_at, expires_at, canonical_reasons)
        return cls(
            deterministic_id("operations_approval", identity),
            request_id,
            operator_id,
            action,
            known_at,
            expires_at,
            canonical_reasons,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class KillSwitchEvent:
    event_id: str
    component: str | None
    action: SwitchAction
    known_at: datetime
    operator_id: str
    reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "kill switch known_at")
        if not all((self.event_id, self.operator_id, self.config_hash)):
            raise ValueError("kill switch identity is required")
        if self.component is not None and self.component not in _COMPONENTS:
            raise ValueError("kill switch component is invalid")
        if self.reasons != _reasons(self.reasons):
            raise ValueError("kill switch reasons must be canonical")

    @classmethod
    def create(
        cls,
        *,
        component: str | None,
        action: SwitchAction,
        known_at: datetime,
        operator_id: str,
        reasons: tuple[str, ...],
        config: OperationsControlConfig,
    ) -> KillSwitchEvent:
        canonical_reasons = _reasons(reasons)
        identity = (component, action, known_at, operator_id, canonical_reasons)
        return cls(
            deterministic_id("operations_kill_switch", identity),
            component,
            action,
            known_at,
            operator_id,
            canonical_reasons,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class CancellationEvent:
    event_id: str
    request_id: str
    action: CancellationAction
    known_at: datetime
    operator_id: str
    reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "cancellation known_at")
        if not all((self.event_id, self.request_id, self.operator_id, self.config_hash)):
            raise ValueError("cancellation identity is required")
        if self.reasons != _reasons(self.reasons):
            raise ValueError("cancellation reasons must be canonical")

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        action: CancellationAction,
        known_at: datetime,
        operator_id: str,
        reasons: tuple[str, ...],
        config: OperationsControlConfig,
    ) -> CancellationEvent:
        canonical_reasons = _reasons(reasons)
        identity = (request_id, action, known_at, operator_id, canonical_reasons)
        return cls(
            deterministic_id("operations_cancellation", identity),
            request_id,
            action,
            known_at,
            operator_id,
            canonical_reasons,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class IncidentEvent:
    event_id: str
    alert_id: str
    action: IncidentAction
    known_at: datetime
    operator_id: str
    reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "incident known_at")
        if not all((self.event_id, self.alert_id, self.operator_id, self.config_hash)):
            raise ValueError("incident identity is required")
        if self.reasons != _reasons(self.reasons):
            raise ValueError("incident reasons must be canonical")

    @classmethod
    def create(
        cls,
        *,
        alert_id: str,
        action: IncidentAction,
        known_at: datetime,
        operator_id: str,
        reasons: tuple[str, ...],
        config: OperationsControlConfig,
    ) -> IncidentEvent:
        canonical_reasons = _reasons(reasons)
        identity = (alert_id, action, known_at, operator_id, canonical_reasons)
        return cls(
            deterministic_id("operations_incident", identity),
            alert_id,
            action,
            known_at,
            operator_id,
            canonical_reasons,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ControlSnapshot:
    snapshot_id: str
    as_of: datetime
    request_id: str | None
    status: ControlStatus
    global_kill_engaged: bool
    component_kills: tuple[str, ...]
    active_operators: tuple[str, ...]
    cancellation_requested: bool
    open_alert_ids: tuple[str, ...]
    acknowledged_alert_ids: tuple[str, ...]
    resolved_alert_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.as_of, "control snapshot as_of")
        if not self.snapshot_id or not self.config_hash:
            raise ValueError("control snapshot identity is required")
        for values in (
            self.component_kills,
            self.active_operators,
            self.open_alert_ids,
            self.acknowledged_alert_ids,
            self.resolved_alert_ids,
            self.reasons,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("control snapshot values must be canonical")

    @classmethod
    def create(
        cls,
        *,
        as_of: datetime,
        request_id: str | None,
        status: ControlStatus,
        global_kill_engaged: bool,
        component_kills: tuple[str, ...],
        active_operators: tuple[str, ...],
        cancellation_requested: bool,
        open_alert_ids: tuple[str, ...],
        acknowledged_alert_ids: tuple[str, ...],
        resolved_alert_ids: tuple[str, ...],
        reasons: tuple[str, ...],
        config_hash: str,
    ) -> ControlSnapshot:
        canonical = tuple(sorted(set(reasons)))
        identity = (
            as_of,
            request_id,
            status,
            global_kill_engaged,
            tuple(sorted(set(component_kills))),
            tuple(sorted(set(active_operators))),
            cancellation_requested,
            tuple(sorted(set(open_alert_ids))),
            tuple(sorted(set(acknowledged_alert_ids))),
            tuple(sorted(set(resolved_alert_ids))),
            canonical,
            config_hash,
        )
        return cls(deterministic_id("operations_control_snapshot", identity), *identity)


class ControlGate(Protocol):
    def authorize(self, request: JobRunRequest, at: datetime) -> ControlSnapshot: ...
