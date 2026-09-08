"""Phase 9A read-only paper operator control reference."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.paper.contracts import RuntimeState
from trading_system.serialization import canonical_hash, deterministic_id


class PaperOperatorConfigError(ValueError):
    pass


class OperatorHealth(StrEnum):
    HEALTHY = "HEALTHY"
    ATTENTION = "ATTENTION"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class PaperOperatorConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class PaperOperatorSnapshot:
    snapshot_id: str
    session_id: str
    observed_at: datetime
    runtime_state: RuntimeState
    health: OperatorHealth
    reason_codes: tuple[str, ...]
    intent_count: int
    incident_count: int
    unmatched_reconciliation_count: int
    latest_heartbeat_at: datetime | None
    latest_checkpoint_at: datetime | None
    replication_status_hash: str | None
    config_hash: str
    control_version: str = "9A.1.0"
    network_used: bool = False
    process_executed: bool = False
    external_notification_sent: bool = False
    research_promotion_performed: bool = False
    broker_write_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.snapshot_id
            or not self.session_id
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() != UTC.utcoffset(self.observed_at)
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or min(
                self.intent_count,
                self.incident_count,
                self.unmatched_reconciliation_count,
            ) < 0
            or any(
                value is not None
                and (value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value))
                for value in (self.latest_heartbeat_at, self.latest_checkpoint_at)
            )
            or (
                self.replication_status_hash is not None
                and not self.replication_status_hash.startswith("sha256:")
            )
            or not self.config_hash.startswith("sha256:")
            or self.control_version != "9A.1.0"
            or any(
                (
                    self.network_used,
                    self.process_executed,
                    self.external_notification_sent,
                    self.research_promotion_performed,
                    self.broker_write_performed,
                    self.production_authority,
                )
            )
        ):
            raise ValueError("invalid Phase 9A operator snapshot")


@dataclass(frozen=True, slots=True)
class PaperOperatorJob:
    job_id: str
    session_id: str
    component: str
    due_at: datetime
    cadence_seconds: int
    config_hash: str
    control_version: str = "9A.1.0"
    planning_only: bool = True

    def __post_init__(self) -> None:
        if (
            not self.job_id
            or not self.session_id
            or self.component not in {
                "PAPER_HEALTH_CHECK",
                "RECONCILIATION_CHECK",
                "REPLICATION_STATUS_CHECK",
            }
            or self.due_at.tzinfo is None
            or self.due_at.utcoffset() != UTC.utcoffset(self.due_at)
            or self.cadence_seconds <= 0
            or not self.config_hash.startswith("sha256:")
            or self.control_version != "9A.1.0"
            or not self.planning_only
        ):
            raise ValueError("invalid Phase 9A operator job")


def load_paper_operator_config(path: str | Path) -> PaperOperatorConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "control_version", "mode", "health", "schedule", "authority"
    }:
        raise PaperOperatorConfigError("Phase 9A configuration keys are invalid")
    if raw["control_version"] != "9A.1.0" or raw["mode"] != (
        "OFFLINE_READ_ONLY_OPERATOR_REFERENCE"
    ):
        raise PaperOperatorConfigError("Phase 9A mode is invalid")
    health = raw["health"]
    if not isinstance(health, dict) or set(health) != {
        "heartbeat_max_age_seconds", "checkpoint_max_age_seconds",
        "heartbeat_required", "checkpoint_required",
        "unmatched_reconciliation_is_attention", "any_incident_is_attention",
    } or not all(isinstance(health[key], int) and health[key] > 0 for key in (
        "heartbeat_max_age_seconds", "checkpoint_max_age_seconds"
    )) or any(health[key] is not True for key in (
        "heartbeat_required", "checkpoint_required",
        "unmatched_reconciliation_is_attention", "any_incident_is_attention",
    )):
        raise PaperOperatorConfigError("Phase 9A health policy is invalid")
    schedule = raw["schedule"]
    if not isinstance(schedule, dict) or set(schedule) != {
        "health_check_cadence_seconds", "reconciliation_check_cadence_seconds",
        "replication_status_check_cadence_seconds",
    } or any(not isinstance(value, int) or value <= 0 for value in schedule.values()):
        raise PaperOperatorConfigError("Phase 9A schedule is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "process_execution_enabled", "network_enabled", "external_notifications_enabled",
        "research_promotion_enabled", "automatic_recovery_enabled",
        "broker_writes_enabled", "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise PaperOperatorConfigError("Phase 9A authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return PaperOperatorConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_operator_jobs(
    config: PaperOperatorConfig,
    *,
    session_id: str,
    anchor_at: datetime,
) -> tuple[PaperOperatorJob, ...]:
    if (
        not session_id
        or anchor_at.tzinfo is None
        or anchor_at.utcoffset() != UTC.utcoffset(anchor_at)
    ):
        raise ValueError("Phase 9A schedule identity and UTC anchor are required")
    schedule = config.values["schedule"]
    if not isinstance(schedule, Mapping):
        raise ValueError("Phase 9A schedule is invalid")
    definitions = (
        ("PAPER_HEALTH_CHECK", int(schedule["health_check_cadence_seconds"])),
        ("RECONCILIATION_CHECK", int(schedule["reconciliation_check_cadence_seconds"])),
        ("REPLICATION_STATUS_CHECK", int(schedule["replication_status_check_cadence_seconds"])),
    )
    return tuple(
        PaperOperatorJob(
            deterministic_id("paper_operator_job", (session_id, component, anchor_at, cadence)),
            session_id,
            component,
            anchor_at + timedelta(seconds=cadence),
            cadence,
            config.config_hash,
        )
        for component, cadence in definitions
    )
