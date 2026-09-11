"""Phase 9T test-only single-use backup-capability rehearsal."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.backup_certification import (
    ProductionBackupReadinessCertificationAssessment,
    ProductionBackupReadinessCertificationRequest,
    ProductionBackupReadinessCertificationState,
)
from trading_system.serialization import canonical_hash, deterministic_id


class BackupCapabilityRehearsalConfigError(ValueError):
    pass


class TestBackupCapabilityState(StrEnum):
    ISSUED = "ISSUED"
    CONSUMED = "CONSUMED"
    BLOCKED = "BLOCKED"


class TestBackupCapabilityEventType(StrEnum):
    ISSUED = "ISSUED"
    CONSUMED = "CONSUMED"
    REPLAY_REJECTED = "REPLAY_REJECTED"
    EXPIRED_REJECTED = "EXPIRED_REJECTED"
    BINDING_REJECTED = "BINDING_REJECTED"


@dataclass(frozen=True, slots=True)
class BackupCapabilityRehearsalConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class TestOnlyBackupCapability:
    capability_id: str
    certification_assessment_id: str
    certification_request_id: str
    certification_request_hash: str
    test_executor_identity: str
    test_nonce: str
    issued_at: datetime
    valid_until: datetime
    state: TestBackupCapabilityState
    config_hash: str
    rehearsal_version: str = "9T.1.0"
    test_only: bool = True
    production_capability: bool = False
    execution_authorized: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    sandbox_execution_enabled: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.capability_id,
                    self.certification_assessment_id,
                    self.certification_request_id,
                    self.test_executor_identity,
                    self.test_nonce,
                )
            )
            or not _sha(self.certification_request_hash)
            or not _sha(self.config_hash)
            or not _utc(self.issued_at)
            or not _utc(self.valid_until)
            or self.issued_at >= self.valid_until
            or self.rehearsal_version != "9T.1.0"
            or not self.test_only
            or any(
                (
                    self.production_capability,
                    self.execution_authorized,
                    self.backup_created,
                    self.database_write_performed,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.sandbox_execution_enabled,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9T test backup capability")


@dataclass(frozen=True, slots=True)
class TestOnlyBackupCapabilityEvent:
    event_id: str
    capability_id: str
    event_type: TestBackupCapabilityEventType
    occurred_at: datetime
    prior_state: TestBackupCapabilityState | None
    new_state: TestBackupCapabilityState
    accepted: bool
    reason_code: str
    certification_request_hash: str
    config_hash: str
    rehearsal_version: str = "9T.1.0"
    operational_action_performed: bool = False
    backup_created: bool = False
    database_write_performed: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        expected_accepted = self.event_type in {
            TestBackupCapabilityEventType.ISSUED,
            TestBackupCapabilityEventType.CONSUMED,
        }
        if (
            not all((self.event_id, self.capability_id, self.reason_code))
            or not _utc(self.occurred_at)
            or not _sha(self.certification_request_hash)
            or not _sha(self.config_hash)
            or self.accepted is not expected_accepted
            or self.rehearsal_version != "9T.1.0"
            or any(
                (
                    self.operational_action_performed,
                    self.backup_created,
                    self.database_write_performed,
                    self.network_used,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9T capability event")


def load_backup_capability_rehearsal_config(
    path: str | Path,
) -> BackupCapabilityRehearsalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "rehearsal_version",
        "mode",
        "certification_config",
        "policy",
        "authority",
    }:
        raise BackupCapabilityRehearsalConfigError("Phase 9T configuration keys are invalid")
    if (
        raw["rehearsal_version"] != "9T.1.0"
        or raw["mode"] != "TEST_ONLY_SINGLE_USE_BACKUP_CAPABILITY_REHEARSAL"
        or not _relative(raw["certification_config"])
    ):
        raise BackupCapabilityRehearsalConfigError(
            "Phase 9T mode or certification path is invalid"
        )
    if raw["policy"] != {
        "require_verified_phase9s_certification": True,
        "require_exact_certification_binding": True,
        "require_test_executor_identity": True,
        "require_test_nonce": True,
        "bounded_capability_window": True,
        "single_use": True,
        "reject_replay": True,
        "append_only_events": True,
    }:
        raise BackupCapabilityRehearsalConfigError("Phase 9T policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "production_capability_enabled",
        "execution_authority_enabled",
        "backup_creation_enabled",
        "directory_creation_enabled",
        "database_write_enabled",
        "migration_execution_enabled",
        "restore_execution_enabled",
        "process_launch_enabled",
        "network_enabled",
        "credential_loading_enabled",
        "broker_writes_enabled",
        "sandbox_execution_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise BackupCapabilityRehearsalConfigError(
            "Phase 9T authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupCapabilityRehearsalConfig(MappingProxyType(frozen), canonical_hash(raw))


def issue_test_backup_capability(
    config: BackupCapabilityRehearsalConfig,
    *,
    certification_request: ProductionBackupReadinessCertificationRequest,
    certification_assessment: ProductionBackupReadinessCertificationAssessment,
    test_executor_identity: str,
    test_nonce: str,
    issued_at: datetime,
    valid_until: datetime,
) -> tuple[TestOnlyBackupCapability, TestOnlyBackupCapabilityEvent]:
    if (
        certification_assessment.state
        is not ProductionBackupReadinessCertificationState.READINESS_CERTIFICATION_EVIDENCE_VERIFIED
    ):
        raise ValueError("Phase 9T requires verified Phase 9S certification evidence")
    if (
        certification_assessment.request_id != certification_request.request_id
        or certification_assessment.request_hash != certification_request.request_hash
        or certification_assessment.config_hash != certification_request.config_hash
    ):
        raise ValueError("Phase 9T certification binding is invalid")
    if not test_executor_identity.strip() or not test_nonce.strip():
        raise ValueError("Phase 9T test executor identity and nonce are required")
    if (
        not _utc(issued_at)
        or not _utc(valid_until)
        or not certification_request.valid_from <= issued_at < valid_until
        or valid_until > certification_request.valid_until
    ):
        raise ValueError("Phase 9T capability window is invalid")
    identity = (
        certification_assessment.assessment_id,
        certification_request.request_id,
        certification_request.request_hash,
        test_executor_identity,
        test_nonce,
        issued_at,
        valid_until,
        config.config_hash,
    )
    capability = TestOnlyBackupCapability(
        deterministic_id("test_backup_capability", identity),
        certification_assessment.assessment_id,
        certification_request.request_id,
        certification_request.request_hash,
        test_executor_identity,
        test_nonce,
        issued_at,
        valid_until,
        TestBackupCapabilityState.ISSUED,
        config.config_hash,
    )
    return capability, _event(
        capability,
        event_type=TestBackupCapabilityEventType.ISSUED,
        occurred_at=issued_at,
        prior_state=None,
        new_state=TestBackupCapabilityState.ISSUED,
        reason_code="TEST_CAPABILITY_ISSUED",
    )


def consume_test_backup_capability(
    capability: TestOnlyBackupCapability,
    *,
    certification_request_hash: str,
    test_executor_identity: str,
    consumed_at: datetime,
) -> tuple[TestOnlyBackupCapability, TestOnlyBackupCapabilityEvent]:
    if not _utc(consumed_at) or consumed_at < capability.issued_at:
        raise ValueError("Phase 9T consumption time must be causal UTC")
    if capability.state is not TestBackupCapabilityState.ISSUED:
        return capability, _event(
            capability,
            event_type=TestBackupCapabilityEventType.REPLAY_REJECTED,
            occurred_at=consumed_at,
            prior_state=capability.state,
            new_state=capability.state,
            reason_code="TEST_CAPABILITY_REPLAY_REJECTED",
        )
    if (
        certification_request_hash != capability.certification_request_hash
        or test_executor_identity != capability.test_executor_identity
    ):
        blocked = replace(capability, state=TestBackupCapabilityState.BLOCKED)
        return blocked, _event(
            capability,
            event_type=TestBackupCapabilityEventType.BINDING_REJECTED,
            occurred_at=consumed_at,
            prior_state=capability.state,
            new_state=blocked.state,
            reason_code="TEST_CAPABILITY_BINDING_REJECTED",
        )
    if consumed_at >= capability.valid_until:
        blocked = replace(capability, state=TestBackupCapabilityState.BLOCKED)
        return blocked, _event(
            capability,
            event_type=TestBackupCapabilityEventType.EXPIRED_REJECTED,
            occurred_at=consumed_at,
            prior_state=capability.state,
            new_state=blocked.state,
            reason_code="TEST_CAPABILITY_EXPIRED",
        )
    consumed = replace(capability, state=TestBackupCapabilityState.CONSUMED)
    return consumed, _event(
        capability,
        event_type=TestBackupCapabilityEventType.CONSUMED,
        occurred_at=consumed_at,
        prior_state=capability.state,
        new_state=consumed.state,
        reason_code="TEST_CAPABILITY_CONSUMED",
    )


def _event(
    capability: TestOnlyBackupCapability,
    *,
    event_type: TestBackupCapabilityEventType,
    occurred_at: datetime,
    prior_state: TestBackupCapabilityState | None,
    new_state: TestBackupCapabilityState,
    reason_code: str,
) -> TestOnlyBackupCapabilityEvent:
    identity = (
        capability.capability_id,
        event_type,
        occurred_at,
        prior_state,
        new_state,
        reason_code,
        capability.certification_request_hash,
        capability.config_hash,
    )
    return TestOnlyBackupCapabilityEvent(
        deterministic_id("test_backup_capability_event", identity),
        capability.capability_id,
        event_type,
        occurred_at,
        prior_state,
        new_state,
        event_type
        in {TestBackupCapabilityEventType.ISSUED, TestBackupCapabilityEventType.CONSUMED},
        reason_code,
        capability.certification_request_hash,
        capability.config_hash,
    )


def _relative(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)
