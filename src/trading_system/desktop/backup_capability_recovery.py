"""Phase 9V test-only receipt persistence and crash-recovery classification."""

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
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityEventType,
    TestBackupCapabilityState,
)
from trading_system.serialization import canonical_hash, deterministic_id


class BackupCapabilityRecoveryConfigError(ValueError):
    pass


class TestBackupReceiptOutcome(StrEnum):
    SIMULATED_SUCCESS = "SIMULATED_SUCCESS"
    SIMULATED_FAILURE = "SIMULATED_FAILURE"


class TestBackupRecoveryState(StrEnum):
    READY_FOR_TEST_CONSUMPTION = "READY_FOR_TEST_CONSUMPTION"
    IN_DOUBT_MANUAL_RECONCILIATION = "IN_DOUBT_MANUAL_RECONCILIATION"
    TEST_COMPLETED = "TEST_COMPLETED"
    TEST_FAILED_REVIEW_REQUIRED = "TEST_FAILED_REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BackupCapabilityRecoveryConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class TestOnlyBackupExecutionReceipt:
    receipt_id: str
    capability_id: str
    consumption_event_id: str
    test_executor_identity: str
    outcome: TestBackupReceiptOutcome
    result_hash: str
    recorded_at: datetime
    config_hash: str
    recovery_version: str = "9V.1.0"
    test_only: bool = True
    backup_created: bool = False
    operator_database_write_performed: bool = False
    automatic_retry_performed: bool = False
    process_launched: bool = False
    network_used: bool = False
    credentials_loaded: bool = False
    broker_write_performed: bool = False
    live_trading_enabled: bool = False

    def __post_init__(self) -> None:
        if (
            not all(
                (
                    self.receipt_id,
                    self.capability_id,
                    self.consumption_event_id,
                    self.test_executor_identity,
                )
            )
            or not _sha(self.result_hash)
            or not _sha(self.config_hash)
            or not _utc(self.recorded_at)
            or self.recovery_version != "9V.1.0"
            or not self.test_only
            or any(
                (
                    self.backup_created,
                    self.operator_database_write_performed,
                    self.automatic_retry_performed,
                    self.process_launched,
                    self.network_used,
                    self.credentials_loaded,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9V test receipt")


@dataclass(frozen=True, slots=True)
class TestBackupRecoveryAssessment:
    assessment_id: str
    capability_id: str
    state: TestBackupRecoveryState
    reason_code: str
    assessed_at: datetime
    receipt_id: str | None
    config_hash: str
    recovery_version: str = "9V.1.0"
    automatic_retry_authorized: bool = False
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
            or not self.reason_code
            or not _utc(self.assessed_at)
            or not _sha(self.config_hash)
            or self.recovery_version != "9V.1.0"
            or any(
                (
                    self.automatic_retry_authorized,
                    self.production_action_authorized,
                    self.backup_created,
                    self.operator_database_write_performed,
                    self.network_used,
                    self.broker_write_performed,
                    self.live_trading_enabled,
                )
            )
        ):
            raise ValueError("invalid Phase 9V recovery assessment")


def load_backup_capability_recovery_config(
    path: str | Path,
) -> BackupCapabilityRecoveryConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "recovery_version",
        "mode",
        "ledger_config",
        "policy",
        "authority",
    }:
        raise BackupCapabilityRecoveryConfigError("Phase 9V configuration keys are invalid")
    if (
        raw["recovery_version"] != "9V.1.0"
        or raw["mode"] != "TEST_ONLY_CAPABILITY_RECEIPT_RECOVERY"
        or not _relative(raw["ledger_config"])
    ):
        raise BackupCapabilityRecoveryConfigError("Phase 9V mode or ledger path is invalid")
    if raw["policy"] != {
        "require_persistent_phase9u_capability": True,
        "require_consumed_state_for_receipt": True,
        "require_exact_consumption_event": True,
        "idempotent_exact_receipt": True,
        "reject_conflicting_receipt": True,
        "missing_receipt_is_in_doubt": True,
        "automatic_retry_disabled": True,
        "restart_recovery_required": True,
    }:
        raise BackupCapabilityRecoveryConfigError("Phase 9V policy is invalid")
    if raw["authority"] != {
        "test_ledger_write_enabled": True,
        "production_receipt_enabled": False,
        "automatic_retry_enabled": False,
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
        raise BackupCapabilityRecoveryConfigError("Phase 9V authority is invalid")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return BackupCapabilityRecoveryConfig(MappingProxyType(frozen), canonical_hash(raw))


class TestOnlyBackupRecoveryJournal:
    """Receipt journal sharing only the contained Phase 9U test database."""

    def __init__(
        self,
        config: BackupCapabilityRecoveryConfig,
        ledger: TestOnlyBackupCapabilityLedger,
    ) -> None:
        self.config = config
        self.ledger = ledger
        self.connection = ledger.connection
        self._initialize()

    def record(
        self, receipt: TestOnlyBackupExecutionReceipt
    ) -> TestOnlyBackupExecutionReceipt:
        expected_receipt = build_test_backup_execution_receipt(
            self.config,
            capability_id=receipt.capability_id,
            consumption_event_id=receipt.consumption_event_id,
            test_executor_identity=receipt.test_executor_identity,
            outcome=receipt.outcome,
            result_hash=receipt.result_hash,
            recorded_at=receipt.recorded_at,
        )
        if receipt.config_hash != self.config.config_hash or receipt != expected_receipt:
            raise ValueError("Phase 9V receipt configuration binding is invalid")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            capability = self.ledger.load(receipt.capability_id)
            if capability is None:
                raise KeyError(f"unknown Phase 9V capability: {receipt.capability_id}")
            events = self.ledger.events(receipt.capability_id)
            consumed = tuple(
                event
                for event in events
                if event.event_type is TestBackupCapabilityEventType.CONSUMED
                and event.accepted
            )
            if (
                capability.state is not TestBackupCapabilityState.CONSUMED
                or len(consumed) != 1
                or consumed[0].event_id != receipt.consumption_event_id
                or capability.test_executor_identity != receipt.test_executor_identity
                or receipt.recorded_at < consumed[0].occurred_at
            ):
                raise ValueError("Phase 9V receipt lacks exact consumed capability evidence")
            existing = self._load(receipt.capability_id)
            if existing is not None:
                if existing != receipt:
                    raise ValueError("Phase 9V receipt conflicts with persisted evidence")
                self.connection.commit()
                return existing
            self.connection.execute(
                """
                INSERT INTO test_backup_execution_receipts
                (receipt_id, capability_id, consumption_event_id, test_executor_identity,
                 outcome, result_hash, recorded_at, config_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.receipt_id,
                    receipt.capability_id,
                    receipt.consumption_event_id,
                    receipt.test_executor_identity,
                    receipt.outcome,
                    receipt.result_hash,
                    receipt.recorded_at.isoformat(),
                    receipt.config_hash,
                ),
            )
            self.connection.commit()
            return receipt
        except Exception:
            self.connection.rollback()
            raise

    def load(self, capability_id: str) -> TestOnlyBackupExecutionReceipt | None:
        return self._load(capability_id)

    def assess(
        self, capability_id: str, *, assessed_at: datetime
    ) -> TestBackupRecoveryAssessment:
        if not _utc(assessed_at):
            raise ValueError("Phase 9V assessment time must be UTC")
        capability = self.ledger.load(capability_id)
        if capability is None:
            raise KeyError(f"unknown Phase 9V capability: {capability_id}")
        if assessed_at < capability.issued_at:
            raise ValueError("Phase 9V assessment time must be causal")
        receipt = self._load(capability_id)
        if capability.state is TestBackupCapabilityState.ISSUED:
            state = TestBackupRecoveryState.READY_FOR_TEST_CONSUMPTION
            reason = "TEST_CAPABILITY_NOT_CONSUMED"
        elif capability.state is TestBackupCapabilityState.BLOCKED:
            state = TestBackupRecoveryState.BLOCKED
            reason = "TEST_CAPABILITY_BLOCKED"
        elif receipt is None:
            state = TestBackupRecoveryState.IN_DOUBT_MANUAL_RECONCILIATION
            reason = "CONSUMED_WITHOUT_TERMINAL_RECEIPT"
        elif receipt.outcome is TestBackupReceiptOutcome.SIMULATED_SUCCESS:
            state = TestBackupRecoveryState.TEST_COMPLETED
            reason = "SIMULATED_TERMINAL_SUCCESS_RECORDED"
        else:
            state = TestBackupRecoveryState.TEST_FAILED_REVIEW_REQUIRED
            reason = "SIMULATED_TERMINAL_FAILURE_RECORDED"
        receipt_id = None if receipt is None else receipt.receipt_id
        identity = (
            capability_id,
            state,
            reason,
            assessed_at,
            receipt_id,
            self.config.config_hash,
        )
        return TestBackupRecoveryAssessment(
            deterministic_id("test_backup_recovery_assessment", identity),
            capability_id,
            state,
            reason,
            assessed_at,
            receipt_id,
            self.config.config_hash,
        )

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS test_backup_recovery_metadata (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                recovery_version TEXT NOT NULL,
                recovery_config_hash TEXT NOT NULL,
                ledger_config_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS test_backup_execution_receipts (
                receipt_id TEXT PRIMARY KEY,
                capability_id TEXT NOT NULL UNIQUE
                    REFERENCES test_backup_capabilities(capability_id),
                consumption_event_id TEXT NOT NULL
                    REFERENCES test_backup_capability_events(event_id),
                test_executor_identity TEXT NOT NULL,
                outcome TEXT NOT NULL,
                result_hash TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                config_hash TEXT NOT NULL
            );
            """
        )
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            expected = ("9V.1.0", self.config.config_hash, self.ledger.config.config_hash)
            row = self.connection.execute(
                "SELECT recovery_version, recovery_config_hash, ledger_config_hash "
                "FROM test_backup_recovery_metadata WHERE singleton = 1"
            ).fetchone()
            if row is None:
                self.connection.execute(
                    "INSERT INTO test_backup_recovery_metadata VALUES (1, ?, ?, ?)",
                    expected,
                )
            elif tuple(str(value) for value in row) != expected:
                raise ValueError("Phase 9V recovery metadata conflicts with configuration")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def _load(self, capability_id: str) -> TestOnlyBackupExecutionReceipt | None:
        row = self.connection.execute(
            """
            SELECT receipt_id, capability_id, consumption_event_id, test_executor_identity,
                   outcome, result_hash, recorded_at, config_hash
            FROM test_backup_execution_receipts WHERE capability_id = ?
            """,
            (capability_id,),
        ).fetchone()
        if row is None:
            return None
        return TestOnlyBackupExecutionReceipt(
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            TestBackupReceiptOutcome(str(row[4])),
            str(row[5]),
            datetime.fromisoformat(str(row[6])),
            str(row[7]),
        )


def build_test_backup_execution_receipt(
    config: BackupCapabilityRecoveryConfig,
    *,
    capability_id: str,
    consumption_event_id: str,
    test_executor_identity: str,
    outcome: TestBackupReceiptOutcome,
    result_hash: str,
    recorded_at: datetime,
) -> TestOnlyBackupExecutionReceipt:
    identity = (
        capability_id,
        consumption_event_id,
        test_executor_identity,
        outcome,
        result_hash,
        recorded_at,
        config.config_hash,
    )
    return TestOnlyBackupExecutionReceipt(
        deterministic_id("test_backup_execution_receipt", identity),
        capability_id,
        consumption_event_id,
        test_executor_identity,
        outcome,
        result_hash,
        recorded_at,
        config.config_hash,
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
