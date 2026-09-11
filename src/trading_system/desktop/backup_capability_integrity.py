"""Phase 9W read-only integrity audit for the isolated test capability ledger."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from trading_system.desktop.backup_capability_ledger import (
    TestOnlyBackupCapabilityLedger,
)
from trading_system.desktop.backup_capability_recovery import (
    TestOnlyBackupRecoveryJournal,
    build_test_backup_execution_receipt,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityEventType,
    TestBackupCapabilityState,
    TestOnlyBackupCapability,
    TestOnlyBackupCapabilityEvent,
)
from trading_system.serialization import canonical_hash, deterministic_id


class BackupCapabilityIntegrityConfigError(ValueError):
    pass


class TestBackupLedgerIntegrityState(StrEnum):
    INTEGRITY_VERIFIED = "INTEGRITY_VERIFIED"
    INTEGRITY_FAILED = "INTEGRITY_FAILED"


@dataclass(frozen=True, slots=True)
class BackupCapabilityIntegrityConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class TestBackupLedgerIntegrityAssessment:
    assessment_id: str
    capability_id: str
    state: TestBackupLedgerIntegrityState
    reasons: tuple[str, ...]
    assessed_at: datetime
    ledger_config_hash: str
    recovery_config_hash: str
    config_hash: str
    audit_version: str = "9W.1.0"
    read_only: bool = True
    repair_performed: bool = False
    production_action_authorized: bool = False
    backup_created: bool = False
    operator_database_write_performed: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not self.assessment_id
            or not self.capability_id
            or not self.reasons
            or tuple(sorted(set(self.reasons))) != self.reasons
            or not _utc(self.assessed_at)
            or not all(_sha(value) for value in (
                self.ledger_config_hash,
                self.recovery_config_hash,
                self.config_hash,
            ))
            or self.audit_version != "9W.1.0"
            or not self.read_only
            or any(
                (
                    self.repair_performed,
                    self.production_action_authorized,
                    self.backup_created,
                    self.operator_database_write_performed,
                    self.network_used,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9W integrity assessment")


def load_backup_capability_integrity_config(
    path: str | Path,
) -> BackupCapabilityIntegrityConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "audit_version",
        "mode",
        "ledger_config",
        "recovery_config",
        "policy",
        "authority",
    }:
        raise BackupCapabilityIntegrityConfigError("Phase 9W configuration keys are invalid")
    if (
        raw["audit_version"] != "9W.1.0"
        or raw["mode"] != "READ_ONLY_TEST_CAPABILITY_LEDGER_INTEGRITY_AUDIT"
        or not _relative(raw["ledger_config"])
        or not _relative(raw["recovery_config"])
    ):
        raise BackupCapabilityIntegrityConfigError("Phase 9W mode or path is invalid")
    if raw["policy"] != {
        "require_sqlite_integrity": True,
        "require_foreign_key_integrity": True,
        "recompute_capability_identity": True,
        "recompute_event_identities": True,
        "require_contiguous_event_sequence": True,
        "require_valid_state_chain": True,
        "recompute_receipt_identity": True,
        "tampering_fails_closed": True,
        "read_only_audit": True,
    }:
        raise BackupCapabilityIntegrityConfigError("Phase 9W policy is invalid")
    if raw["authority"] != {
        "test_ledger_write_enabled": False,
        "repair_enabled": False,
        "production_audit_enabled": False,
        "operator_database_access_enabled": False,
        "backup_creation_enabled": False,
        "database_migration_enabled": False,
        "restore_execution_enabled": False,
        "process_launch_enabled": False,
        "network_enabled": False,
        "credential_loading_enabled": False,
        "broker_writes_enabled": False,
        "sandbox_execution_enabled": False,
        "live_trading_enabled": False,
    }:
        raise BackupCapabilityIntegrityConfigError("Phase 9W authority is invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupCapabilityIntegrityConfig(MappingProxyType(frozen), canonical_hash(raw))


def audit_test_backup_capability_ledger(
    config: BackupCapabilityIntegrityConfig,
    *,
    ledger: TestOnlyBackupCapabilityLedger,
    recovery: TestOnlyBackupRecoveryJournal,
    capability_id: str,
    assessed_at: datetime,
) -> TestBackupLedgerIntegrityAssessment:
    if not _utc(assessed_at):
        raise ValueError("Phase 9W assessment time must be UTC")
    reasons: set[str] = set()
    connection = ledger.connection
    if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        reasons.add("SQLITE_INTEGRITY_FAILED")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        reasons.add("FOREIGN_KEY_INTEGRITY_FAILED")
    row = connection.execute(
        """
        SELECT capability_id, certification_assessment_id, certification_request_id,
               certification_request_hash, test_executor_identity, test_nonce, issued_at,
               valid_until, state, config_hash
        FROM test_backup_capabilities WHERE capability_id = ?
        """,
        (capability_id,),
    ).fetchone()
    if row is None:
        reasons.add("CAPABILITY_MISSING")
        return _assessment(config, ledger, recovery, capability_id, assessed_at, reasons)
    try:
        capability = _capability(row)
    except (TypeError, ValueError):
        reasons.add("CAPABILITY_RECORD_INVALID")
        return _assessment(config, ledger, recovery, capability_id, assessed_at, reasons)
    if assessed_at < capability.issued_at:
        raise ValueError("Phase 9W assessment time must be causal")
    expected_capability_id = deterministic_id(
        "test_backup_capability",
        (
            capability.certification_assessment_id,
            capability.certification_request_id,
            capability.certification_request_hash,
            capability.test_executor_identity,
            capability.test_nonce,
            capability.issued_at,
            capability.valid_until,
            capability.config_hash,
        ),
    )
    if capability.capability_id != expected_capability_id:
        reasons.add("CAPABILITY_IDENTITY_MISMATCH")
    event_rows = connection.execute(
        """
        SELECT sequence, event_id, capability_id, event_type, occurred_at, prior_state,
               new_state, accepted, reason_code, certification_request_hash, config_hash
        FROM test_backup_capability_events WHERE capability_id = ? ORDER BY sequence
        """,
        (capability_id,),
    ).fetchall()
    events: list[TestOnlyBackupCapabilityEvent] = []
    if tuple(int(row[0]) for row in event_rows) != tuple(range(1, len(event_rows) + 1)):
        reasons.add("EVENT_SEQUENCE_INVALID")
    for event_row in event_rows:
        try:
            event = _event(event_row[1:])
        except (TypeError, ValueError):
            reasons.add("EVENT_RECORD_INVALID")
            continue
        events.append(event)
        expected_event_id = deterministic_id(
            "test_backup_capability_event",
            (
                event.capability_id,
                event.event_type,
                event.occurred_at,
                event.prior_state,
                event.new_state,
                event.reason_code,
                event.certification_request_hash,
                event.config_hash,
            ),
        )
        if event.event_id != expected_event_id:
            reasons.add("EVENT_IDENTITY_MISMATCH")
    if not _valid_chain(capability, events):
        reasons.add("EVENT_STATE_CHAIN_INVALID")
    receipt = recovery.load(capability_id)
    if receipt is not None:
        expected_receipt = build_test_backup_execution_receipt(
            recovery.config,
            capability_id=receipt.capability_id,
            consumption_event_id=receipt.consumption_event_id,
            test_executor_identity=receipt.test_executor_identity,
            outcome=receipt.outcome,
            result_hash=receipt.result_hash,
            recorded_at=receipt.recorded_at,
        )
        if receipt != expected_receipt:
            reasons.add("RECEIPT_IDENTITY_MISMATCH")
        consumed_ids = {
            event.event_id
            for event in events
            if event.event_type is TestBackupCapabilityEventType.CONSUMED and event.accepted
        }
        if (
            receipt.consumption_event_id not in consumed_ids
            or receipt.test_executor_identity != capability.test_executor_identity
        ):
            reasons.add("RECEIPT_BINDING_INVALID")
    if not reasons:
        reasons.add("TEST_LEDGER_INTEGRITY_VERIFIED")
    return _assessment(config, ledger, recovery, capability_id, assessed_at, reasons)


def _valid_chain(
    capability: TestOnlyBackupCapability,
    events: list[TestOnlyBackupCapabilityEvent],
) -> bool:
    if (
        not events
        or events[0].event_type is not TestBackupCapabilityEventType.ISSUED
        or events[0].prior_state is not None
        or events[0].new_state is not TestBackupCapabilityState.ISSUED
        or events[0].occurred_at != capability.issued_at
    ):
        return False
    state = TestBackupCapabilityState.ISSUED
    previous_time = capability.issued_at
    for event in events:
        if (
            event.capability_id != capability.capability_id
            or event.certification_request_hash != capability.certification_request_hash
            or event.config_hash != capability.config_hash
            or event.occurred_at < previous_time
        ):
            return False
        previous_time = event.occurred_at
    for event in events[1:]:
        if event.prior_state is not state:
            return False
        if event.event_type is TestBackupCapabilityEventType.CONSUMED:
            if state is not TestBackupCapabilityState.ISSUED:
                return False
            state = TestBackupCapabilityState.CONSUMED
        elif event.event_type in {
            TestBackupCapabilityEventType.EXPIRED_REJECTED,
            TestBackupCapabilityEventType.BINDING_REJECTED,
        }:
            if state is not TestBackupCapabilityState.ISSUED:
                return False
            state = TestBackupCapabilityState.BLOCKED
        elif event.event_type is TestBackupCapabilityEventType.REPLAY_REJECTED:
            if event.new_state is not state:
                return False
        else:
            return False
        if event.new_state is not state:
            return False
    return state is capability.state


def _assessment(
    config: BackupCapabilityIntegrityConfig,
    ledger: TestOnlyBackupCapabilityLedger,
    recovery: TestOnlyBackupRecoveryJournal,
    capability_id: str,
    assessed_at: datetime,
    reasons: set[str],
) -> TestBackupLedgerIntegrityAssessment:
    ordered = tuple(sorted(reasons))
    state = (
        TestBackupLedgerIntegrityState.INTEGRITY_VERIFIED
        if ordered == ("TEST_LEDGER_INTEGRITY_VERIFIED",)
        else TestBackupLedgerIntegrityState.INTEGRITY_FAILED
    )
    identity = (
        capability_id,
        state,
        ordered,
        assessed_at,
        ledger.config.config_hash,
        recovery.config.config_hash,
        config.config_hash,
    )
    return TestBackupLedgerIntegrityAssessment(
        deterministic_id("test_backup_ledger_integrity_assessment", identity),
        capability_id,
        state,
        ordered,
        assessed_at,
        ledger.config.config_hash,
        recovery.config.config_hash,
        config.config_hash,
    )


def _capability(row: tuple[object, ...]) -> TestOnlyBackupCapability:
    return TestOnlyBackupCapability(
        str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]), str(row[5]),
        datetime.fromisoformat(str(row[6])), datetime.fromisoformat(str(row[7])),
        TestBackupCapabilityState(str(row[8])), str(row[9]),
    )


def _event(row: tuple[object, ...]) -> TestOnlyBackupCapabilityEvent:
    prior = None if row[4] is None else TestBackupCapabilityState(str(row[4]))
    return TestOnlyBackupCapabilityEvent(
        str(row[0]), str(row[1]), TestBackupCapabilityEventType(str(row[2])),
        datetime.fromisoformat(str(row[3])), prior,
        TestBackupCapabilityState(str(row[5])), bool(row[6]), str(row[7]), str(row[8]),
        str(row[9]),
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
