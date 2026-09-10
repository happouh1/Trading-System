"""Phase 9F offline sandbox supervision leases without execution authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.paper.rollout import StagedRolloutPlan
from trading_system.paper.stage_authorization import (
    StageAuthorizationAssessment,
    StageAuthorizationState,
)
from trading_system.serialization import canonical_hash, deterministic_id


class SandboxLeaseConfigError(ValueError):
    pass


class SandboxLeaseState(StrEnum):
    SCHEDULED = "SCHEDULED"
    SUPERVISION_WINDOW_OPEN = "SUPERVISION_WINDOW_OPEN"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class SandboxLeaseConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class SandboxStageLease:
    lease_id: str
    session_id: str
    authorization_assessment_id: str
    authorization_assessment_hash: str
    plan_id: str
    plan_hash: str
    stage_id: str
    issued_at: datetime
    valid_from: datetime
    valid_until: datetime
    capital_ceiling: Decimal
    position_ceiling: int
    lease_hash: str
    config_hash: str
    lease_version: str = "9F.1.0"
    process_launch_authorized: bool = False
    network_authorized: bool = False
    broker_write_authorized: bool = False
    sandbox_execution_authorized: bool = False
    live_trading_authorized: bool = False

    def __post_init__(self) -> None:
        timestamps = (self.issued_at, self.valid_from, self.valid_until)
        if (
            not all((self.lease_id, self.session_id, self.authorization_assessment_id,
                     self.plan_id, self.stage_id))
            or not self.authorization_assessment_hash.startswith("sha256:")
            or not self.plan_hash.startswith("sha256:")
            or any(
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
                for value in timestamps
            )
            or not self.issued_at <= self.valid_from < self.valid_until
            or self.capital_ceiling <= 0
            or self.position_ceiling < 1
            or not self.lease_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.lease_version != "9F.1.0"
            or self.process_launch_authorized
            or self.network_authorized
            or self.broker_write_authorized
            or self.sandbox_execution_authorized
            or self.live_trading_authorized
        ):
            raise ValueError("invalid Phase 9F sandbox supervision lease")


@dataclass(frozen=True, slots=True)
class SandboxLeaseRevocation:
    revocation_id: str
    lease_id: str
    lease_hash: str
    revoked_at: datetime
    reason_code: str

    def __post_init__(self) -> None:
        if (
            not all((self.revocation_id, self.lease_id, self.reason_code))
            or not self.lease_hash.startswith("sha256:")
            or self.revoked_at.tzinfo is None
            or self.revoked_at.utcoffset() != UTC.utcoffset(self.revoked_at)
        ):
            raise ValueError("invalid Phase 9F lease revocation")


@dataclass(frozen=True, slots=True)
class SandboxLeaseAssessment:
    assessment_id: str
    lease_id: str
    evaluated_at: datetime
    state: SandboxLeaseState
    reason_codes: tuple[str, ...]
    lease_hash: str
    revocation_hash: str | None
    config_hash: str
    lease_version: str = "9F.1.0"
    process_launched: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.lease_id
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() != UTC.utcoffset(self.evaluated_at)
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or not self.lease_hash.startswith("sha256:")
            or (self.revocation_hash is not None and not self.revocation_hash.startswith("sha256:"))
            or not self.config_hash.startswith("sha256:")
            or self.lease_version != "9F.1.0"
            or self.process_launched
            or self.network_used
            or self.broker_write_performed
            or self.sandbox_execution_enabled
            or self.live_trading_enabled
        ):
            raise ValueError("invalid Phase 9F lease assessment")


def load_sandbox_lease_config(path: str | Path) -> SandboxLeaseConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "lease_version", "mode", "policy", "authority"
    }:
        raise SandboxLeaseConfigError("Phase 9F configuration keys are invalid")
    if raw["lease_version"] != "9F.1.0" or raw["mode"] != (
        "OFFLINE_SANDBOX_SUPERVISION_LEASE"
    ):
        raise SandboxLeaseConfigError("Phase 9F mode is invalid")
    if raw["policy"] != {
        "require_phase9e_signatures_verified": True,
        "exact_plan_and_stage_scope": True,
        "lease_window_operator_supplied": True,
        "limits_inherited_from_phase9d": True,
        "revocation_reason_required": True,
        "status_is_causal": True,
    }:
        raise SandboxLeaseConfigError("Phase 9F policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or any(value is not False for value in authority.values()):
        raise SandboxLeaseConfigError("Phase 9F authority must remain disabled")
    if set(authority) != {
        "lease_defaults_enabled", "process_launch_enabled", "network_enabled",
        "broker_writes_enabled", "sandbox_execution_enabled", "deployment_enabled",
        "live_trading_enabled",
    }:
        raise SandboxLeaseConfigError("Phase 9F authority keys are invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return SandboxLeaseConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_sandbox_stage_lease(
    config: SandboxLeaseConfig,
    *,
    authorization: StageAuthorizationAssessment,
    plan: StagedRolloutPlan,
    issued_at: datetime,
    valid_from: datetime,
    valid_until: datetime,
) -> SandboxStageLease:
    if authorization.state is not StageAuthorizationState.SIGNATURES_VERIFIED:
        raise ValueError("Phase 9F requires Phase 9E verified signatures")
    if authorization.plan_id != plan.plan_id or authorization.stage_id not in {
        stage.stage_id for stage in plan.stages
    }:
        raise ValueError("Phase 9F authorization scope does not match the rollout plan")
    stage = next(stage for stage in plan.stages if stage.stage_id == authorization.stage_id)
    content = (
        plan.session_id, authorization.assessment_id, canonical_hash(authorization),
        plan.plan_id, plan.plan_hash, stage.stage_id, issued_at, valid_from, valid_until,
        stage.capital_ceiling, stage.position_ceiling, config.config_hash,
    )
    return SandboxStageLease(
        deterministic_id("sandbox_stage_lease", content), plan.session_id,
        authorization.assessment_id, canonical_hash(authorization), plan.plan_id,
        plan.plan_hash, stage.stage_id, issued_at, valid_from, valid_until,
        stage.capital_ceiling, stage.position_ceiling, canonical_hash(content),
        config.config_hash,
    )


def build_sandbox_lease_revocation(
    lease: SandboxStageLease,
    *,
    revoked_at: datetime,
    reason_code: str,
) -> SandboxLeaseRevocation:
    if revoked_at < lease.issued_at:
        raise ValueError("Phase 9F revocation predates lease issuance")
    identity = (lease.lease_id, lease.lease_hash, revoked_at, reason_code)
    return SandboxLeaseRevocation(
        deterministic_id("sandbox_lease_revocation", identity), lease.lease_id,
        lease.lease_hash, revoked_at, reason_code,
    )


def evaluate_sandbox_lease(
    lease: SandboxStageLease,
    *,
    evaluated_at: datetime,
    revocation: SandboxLeaseRevocation | None = None,
) -> SandboxLeaseAssessment:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise ValueError("Phase 9F evaluation time must be UTC")
    if revocation is not None and (
        revocation.lease_id != lease.lease_id or revocation.lease_hash != lease.lease_hash
    ):
        raise ValueError("Phase 9F revocation belongs to another lease")
    if revocation is not None and revocation.revoked_at > evaluated_at:
        raise ValueError("Phase 9F future revocation is not causally available")
    reasons: tuple[str, ...]
    if revocation is not None:
        state = SandboxLeaseState.REVOKED
        reasons = ("LEASE_REVOKED",)
        revocation_hash = canonical_hash(revocation)
    elif evaluated_at < lease.valid_from:
        state = SandboxLeaseState.SCHEDULED
        reasons = ("LEASE_NOT_YET_EFFECTIVE",)
        revocation_hash = None
    elif evaluated_at >= lease.valid_until:
        state = SandboxLeaseState.EXPIRED
        reasons = ("LEASE_EXPIRED",)
        revocation_hash = None
    else:
        state = SandboxLeaseState.SUPERVISION_WINDOW_OPEN
        reasons = ()
        revocation_hash = None
    identity = (
        lease.lease_id, evaluated_at, state, reasons, lease.lease_hash, revocation_hash,
    )
    return SandboxLeaseAssessment(
        deterministic_id("sandbox_lease_assessment", identity), lease.lease_id,
        evaluated_at, state, reasons, lease.lease_hash, revocation_hash, lease.config_hash,
    )
