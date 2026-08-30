"""Deterministic Phase 5B schedule planning and internal health alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from trading_system.operations.monitor_config import OperationsMonitorConfig
from trading_system.serialization import canonical_json, deterministic_id

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


class OperationalMode(StrEnum):
    OFFLINE = "OFFLINE"
    SHADOW = "SHADOW"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class MonitorStatus(StrEnum):
    HEALTHY = "HEALTHY"
    ATTENTION = "ATTENTION"


class AlertSeverity(StrEnum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertKind(StrEnum):
    SCHEDULE_OVERDUE = "SCHEDULE_OVERDUE"
    HEALTH_STALE = "HEALTH_STALE"
    COMPONENT_DEGRADED = "COMPONENT_DEGRADED"
    COMPONENT_FAILED = "COMPONENT_FAILED"


@dataclass(frozen=True, slots=True)
class ScheduleDefinition:
    job_id: str
    name: str
    component: str
    mode: OperationalMode
    first_due_at: datetime
    cadence_seconds: int
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.first_due_at, "first_due_at")
        if not all((self.job_id, self.name, self.config_hash)):
            raise ValueError("schedule identity is required")
        if self.component not in _COMPONENTS:
            raise ValueError("schedule component is invalid")
        if self.cadence_seconds <= 0:
            raise ValueError("schedule cadence must be positive")

    @classmethod
    def create(
        cls,
        *,
        name: str,
        component: str,
        mode: OperationalMode,
        first_due_at: datetime,
        cadence_seconds: int,
        config_hash: str,
    ) -> ScheduleDefinition:
        identity = (name, component, mode, first_due_at, cadence_seconds, config_hash)
        return cls(
            deterministic_id("operations_schedule", identity),
            name,
            component,
            mode,
            first_due_at,
            cadence_seconds,
            config_hash,
        )


@dataclass(frozen=True, slots=True)
class ScheduleCursor:
    job_id: str
    last_completed_at: datetime | None

    def __post_init__(self) -> None:
        if not self.job_id:
            raise ValueError("schedule cursor job identity is required")
        if self.last_completed_at is not None:
            _aware(self.last_completed_at, "last_completed_at")


@dataclass(frozen=True, slots=True)
class DueJob:
    job_id: str
    due_at: datetime
    overdue_seconds: int

    def __post_init__(self) -> None:
        _aware(self.due_at, "due_at")
        if not self.job_id or self.overdue_seconds < 0:
            raise ValueError("due job values are invalid")


@dataclass(frozen=True, slots=True)
class SchedulePlan:
    plan_id: str
    as_of: datetime
    due_jobs: tuple[DueJob, ...]
    next_due: tuple[tuple[str, datetime], ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.as_of, "schedule plan as_of")
        if not self.plan_id or not self.config_hash:
            raise ValueError("schedule plan identity is required")
        if tuple(sorted(self.due_jobs, key=lambda item: item.job_id)) != self.due_jobs:
            raise ValueError("due jobs must be in canonical order")
        if len({item.job_id for item in self.due_jobs}) != len(self.due_jobs):
            raise ValueError("due job identities must be unique")
        if tuple(sorted(self.next_due, key=lambda item: item[0])) != self.next_due:
            raise ValueError("next due values must be in canonical order")
        if len({job_id for job_id, _ in self.next_due}) != len(self.next_due):
            raise ValueError("next due identities must be unique")
        for job_id, due_at in self.next_due:
            if not job_id:
                raise ValueError("next due job identity is required")
            _aware(due_at, "next due timestamp")


@dataclass(frozen=True, slots=True)
class HealthObservation:
    observation_id: str
    component: str
    observed_at: datetime
    status: HealthStatus
    reasons: tuple[str, ...]
    evidence_fingerprint: str
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.observed_at, "health observed_at")
        if not all((self.observation_id, self.evidence_fingerprint, self.config_hash)):
            raise ValueError("health observation identity is required")
        if self.component not in _COMPONENTS:
            raise ValueError("health component is invalid")
        if self.status is HealthStatus.HEALTHY and self.reasons:
            raise ValueError("healthy observation cannot contain reasons")
        if self.status is not HealthStatus.HEALTHY and not self.reasons:
            raise ValueError("unhealthy observation requires reasons")

    @classmethod
    def create(
        cls,
        *,
        component: str,
        observed_at: datetime,
        status: HealthStatus,
        reasons: tuple[str, ...],
        evidence_fingerprint: str,
        config_hash: str,
    ) -> HealthObservation:
        canonical_reasons = tuple(sorted(set(reasons)))
        identity = (
            component,
            observed_at,
            status,
            canonical_reasons,
            evidence_fingerprint,
            config_hash,
        )
        return cls(
            deterministic_id("operations_health", identity),
            component,
            observed_at,
            status,
            canonical_reasons,
            evidence_fingerprint,
            config_hash,
        )


@dataclass(frozen=True, slots=True)
class InternalAlert:
    alert_id: str
    known_at: datetime
    component: str
    kind: AlertKind
    severity: AlertSeverity
    source_id: str
    reasons: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "alert known_at")
        if not all((self.alert_id, self.source_id, self.config_hash)):
            raise ValueError("alert identity is required")
        if self.component not in _COMPONENTS:
            raise ValueError("alert component is invalid")
        if not self.reasons:
            raise ValueError("alert reasons are required")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("alert reasons must be canonical")

    @classmethod
    def create(
        cls,
        *,
        known_at: datetime,
        component: str,
        kind: AlertKind,
        severity: AlertSeverity,
        source_id: str,
        reasons: tuple[str, ...],
        config_hash: str,
    ) -> InternalAlert:
        _aware(known_at, "alert known_at")
        canonical_reasons = tuple(sorted(set(reasons)))
        identity = (
            known_at,
            component,
            kind,
            severity,
            source_id,
            canonical_reasons,
            config_hash,
        )
        return cls(
            deterministic_id("operations_alert", identity),
            known_at,
            component,
            kind,
            severity,
            source_id,
            canonical_reasons,
            config_hash,
        )


@dataclass(frozen=True, slots=True)
class MonitorReport:
    report_id: str
    as_of: datetime
    status: MonitorStatus
    schedule_plan_id: str
    health_observation_ids: tuple[str, ...]
    alert_ids: tuple[str, ...]
    source_revision: str
    config_hash: str
    disclosures: tuple[str, ...]

    def __post_init__(self) -> None:
        _aware(self.as_of, "monitor report as_of")
        if not all(
            (
                self.report_id,
                self.schedule_plan_id,
                self.source_revision,
                self.config_hash,
            )
        ):
            raise ValueError("monitor report identity is required")
        if len(self.health_observation_ids) != len(_COMPONENTS):
            raise ValueError("monitor report requires all component health observations")
        if len(set(self.health_observation_ids)) != len(self.health_observation_ids):
            raise ValueError("monitor health observation identities must be unique")
        if self.health_observation_ids != tuple(sorted(self.health_observation_ids)):
            raise ValueError("monitor health observation identities must be canonical")
        if self.alert_ids != tuple(sorted(set(self.alert_ids))):
            raise ValueError("monitor alert identities must be canonical")
        required_disclosures = {
            "PLANNING_ONLY_NO_PROCESS_EXECUTION",
            "INTERNAL_ALERT_JOURNAL_NO_EXTERNAL_NOTIFICATION",
            "OFFLINE_AND_SHADOW_MODES_ONLY",
            "NO_NETWORK_CREDENTIAL_OR_BROKER_AUTHORITY",
        }
        if set(self.disclosures) != required_disclosures:
            raise ValueError("monitor report authority disclosures are invalid")

    def to_json(self) -> str:
        return canonical_json(self)


class OperationsMonitorEngine:
    def __init__(self, config: OperationsMonitorConfig) -> None:
        self.config = config

    def evaluate(
        self,
        *,
        as_of: datetime,
        schedules: tuple[ScheduleDefinition, ...],
        cursors: tuple[ScheduleCursor, ...],
        health: tuple[HealthObservation, ...],
        source_revision: str,
    ) -> tuple[MonitorReport, SchedulePlan, tuple[InternalAlert, ...]]:
        _aware(as_of, "monitor as_of")
        if not source_revision:
            raise ValueError("monitor source revision is required")
        if not schedules or len(schedules) > self.config.maximum_jobs:
            raise ValueError("schedule count is outside configured bounds")
        jobs = {item.job_id: item for item in schedules}
        if len(jobs) != len(schedules):
            raise ValueError("schedule identities must be unique")
        for job in schedules:
            if job.config_hash != self.config.config_hash:
                raise ValueError("schedule configuration hash mismatch")
            if not (
                self.config.minimum_cadence_seconds
                <= job.cadence_seconds
                <= self.config.maximum_cadence_seconds
            ):
                raise ValueError("schedule cadence is outside configured bounds")
        cursor_map = {item.job_id: item for item in cursors}
        if len(cursor_map) != len(cursors) or not set(cursor_map).issubset(jobs):
            raise ValueError("schedule cursors must be unique and reference declared jobs")
        if any(
            item.last_completed_at is not None and item.last_completed_at > as_of
            for item in cursors
        ):
            raise ValueError("future schedule completion timestamps are prohibited")
        health_map = {item.component: item for item in health}
        if len(health_map) != len(health) or set(health_map) != _COMPONENTS:
            raise ValueError("health requires exactly all Phase 5A components")
        if any(item.config_hash != self.config.config_hash for item in health):
            raise ValueError("health configuration hash mismatch")
        if any(item.observed_at > as_of for item in health):
            raise ValueError("future health observations are prohibited")

        due: list[DueJob] = []
        next_due: list[tuple[str, datetime]] = []
        alerts: list[InternalAlert] = []
        for job in sorted(schedules, key=lambda item: item.job_id):
            if as_of < job.first_due_at:
                next_due.append((job.job_id, job.first_due_at))
                continue
            elapsed = int((as_of - job.first_due_at).total_seconds())
            intervals = elapsed // job.cadence_seconds
            latest_due = job.first_due_at + timedelta(seconds=intervals * job.cadence_seconds)
            next_due.append((job.job_id, latest_due + timedelta(seconds=job.cadence_seconds)))
            cursor = cursor_map.get(job.job_id)
            last_completed = None if cursor is None else cursor.last_completed_at
            if last_completed is None or last_completed < latest_due:
                overdue = int((as_of - latest_due).total_seconds())
                due_job = DueJob(job.job_id, latest_due, overdue)
                due.append(due_job)
                if overdue > self.config.overdue_grace_seconds:
                    alerts.append(
                        InternalAlert.create(
                            known_at=as_of,
                            component=job.component,
                            kind=AlertKind.SCHEDULE_OVERDUE,
                            severity=AlertSeverity.WARNING,
                            source_id=job.job_id,
                            reasons=(f"OVERDUE_SECONDS:{overdue}",),
                            config_hash=self.config.config_hash,
                        )
                    )
        due_tuple = tuple(due)
        next_due_tuple = tuple(next_due)
        plan_id = deterministic_id(
            "operations_schedule_plan",
            (as_of, due_tuple, next_due_tuple, self.config.config_hash),
        )
        plan = SchedulePlan(plan_id, as_of, due_tuple, next_due_tuple, self.config.config_hash)

        ordered_health = tuple(sorted(health, key=lambda item: item.component))
        for observation in ordered_health:
            age = int((as_of - observation.observed_at).total_seconds())
            if age > self.config.maximum_health_age_seconds:
                alerts.append(
                    InternalAlert.create(
                        known_at=as_of,
                        component=observation.component,
                        kind=AlertKind.HEALTH_STALE,
                        severity=AlertSeverity.WARNING,
                        source_id=observation.observation_id,
                        reasons=(f"AGE_SECONDS:{age}",),
                        config_hash=self.config.config_hash,
                    )
                )
            if observation.status is HealthStatus.DEGRADED:
                alerts.append(
                    InternalAlert.create(
                        known_at=as_of,
                        component=observation.component,
                        kind=AlertKind.COMPONENT_DEGRADED,
                        severity=AlertSeverity.WARNING,
                        source_id=observation.observation_id,
                        reasons=observation.reasons,
                        config_hash=self.config.config_hash,
                    )
                )
            elif observation.status is HealthStatus.FAILED:
                alerts.append(
                    InternalAlert.create(
                        known_at=as_of,
                        component=observation.component,
                        kind=AlertKind.COMPONENT_FAILED,
                        severity=AlertSeverity.CRITICAL,
                        source_id=observation.observation_id,
                        reasons=observation.reasons,
                        config_hash=self.config.config_hash,
                    )
                )
        alert_tuple = tuple(sorted(alerts, key=lambda item: item.alert_id))
        health_ids = tuple(sorted(item.observation_id for item in ordered_health))
        alert_ids = tuple(item.alert_id for item in alert_tuple)
        report_id = deterministic_id(
            "operations_monitor_report",
            (as_of, plan.plan_id, health_ids, alert_ids, source_revision, self.config.config_hash),
        )
        report = MonitorReport(
            report_id,
            as_of,
            MonitorStatus.ATTENTION if alert_tuple or due_tuple else MonitorStatus.HEALTHY,
            plan.plan_id,
            health_ids,
            alert_ids,
            source_revision,
            self.config.config_hash,
            (
                "PLANNING_ONLY_NO_PROCESS_EXECUTION",
                "INTERNAL_ALERT_JOURNAL_NO_EXTERNAL_NOTIFICATION",
                "OFFLINE_AND_SHADOW_MODES_ONLY",
                "NO_NETWORK_CREDENTIAL_OR_BROKER_AUTHORITY",
            ),
        )
        return report, plan, alert_tuple
