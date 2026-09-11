from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop.backup_capability_ledger import (
    TestOnlyBackupCapabilityLedger as BackupCapabilityLedger,
)
from trading_system.desktop.backup_capability_ledger import (
    bind_backup_capability_config_hash,
    load_backup_capability_ledger_config,
)
from trading_system.desktop.backup_capability_recovery import (
    BackupCapabilityRecoveryConfigError,
    build_test_backup_execution_receipt,
    load_backup_capability_recovery_config,
)
from trading_system.desktop.backup_capability_recovery import (
    TestBackupReceiptOutcome as ReceiptOutcome,
)
from trading_system.desktop.backup_capability_recovery import (
    TestBackupRecoveryState as RecoveryState,
)
from trading_system.desktop.backup_capability_recovery import (
    TestOnlyBackupRecoveryJournal as RecoveryJournal,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityEventType as CapabilityEventType,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityState as CapabilityState,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestOnlyBackupCapability as BackupCapability,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestOnlyBackupCapabilityEvent as BackupCapabilityEvent,
)
from trading_system.desktop.backup_capability_rehearsal import (
    load_backup_capability_rehearsal_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9v.v1.yaml"
LEDGER_CONFIG = ROOT / "config/desktop.phase9u.v1.yaml"
CAPABILITY_CONFIG = ROOT / "config/desktop.phase9t.v1.yaml"
NOW = datetime(2026, 9, 11, 18, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
DATABASE = ".p9u-capability-ledger/phase9v.sqlite"


def _ledger(tmp_path: Path) -> BackupCapabilityLedger:
    capability_config = load_backup_capability_rehearsal_config(CAPABILITY_CONFIG)
    config = bind_backup_capability_config_hash(
        load_backup_capability_ledger_config(LEDGER_CONFIG),
        capability_config.config_hash,
    )
    return BackupCapabilityLedger(
        config, project_root=tmp_path, database_path=DATABASE
    )


def _issued() -> tuple[BackupCapability, BackupCapabilityEvent]:
    config_hash = load_backup_capability_rehearsal_config(CAPABILITY_CONFIG).config_hash
    capability = BackupCapability(
        "phase9v-test-capability",
        "phase9s-assessment",
        "phase9s-request",
        HASH_A,
        "test-executor",
        "phase9v-nonce",
        NOW,
        NOW + timedelta(minutes=10),
        CapabilityState.ISSUED,
        config_hash,
    )
    event = BackupCapabilityEvent(
        "phase9v-issued-event",
        capability.capability_id,
        CapabilityEventType.ISSUED,
        NOW,
        None,
        CapabilityState.ISSUED,
        True,
        "TEST_CAPABILITY_ISSUED",
        HASH_A,
        config_hash,
    )
    return capability, event


def _consume(
    ledger: BackupCapabilityLedger,
) -> tuple[BackupCapability, BackupCapabilityEvent]:
    return ledger.consume(
        "phase9v-test-capability",
        certification_request_hash=HASH_A,
        test_executor_identity="test-executor",
        consumed_at=NOW + timedelta(minutes=1),
    )


def test_issued_capability_is_ready_but_never_authorized(tmp_path: Path) -> None:
    capability, event = _issued()
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        journal = RecoveryJournal(
            load_backup_capability_recovery_config(CONFIG), ledger
        )
        assessment = journal.assess(
            capability.capability_id, assessed_at=NOW + timedelta(seconds=1)
        )
    assert assessment.state is RecoveryState.READY_FOR_TEST_CONSUMPTION
    assert not assessment.automatic_retry_authorized
    assert not assessment.production_action_authorized


def test_consumed_without_receipt_is_in_doubt_after_restart(tmp_path: Path) -> None:
    capability, event = _issued()
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        _consume(ledger)
    with _ledger(tmp_path) as restarted:
        journal = RecoveryJournal(
            load_backup_capability_recovery_config(CONFIG), restarted
        )
        assessment = journal.assess(
            capability.capability_id, assessed_at=NOW + timedelta(minutes=2)
        )
    assert assessment.state is RecoveryState.IN_DOUBT_MANUAL_RECONCILIATION
    assert assessment.reason_code == "CONSUMED_WITHOUT_TERMINAL_RECEIPT"


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (ReceiptOutcome.SIMULATED_SUCCESS, RecoveryState.TEST_COMPLETED),
        (
            ReceiptOutcome.SIMULATED_FAILURE,
            RecoveryState.TEST_FAILED_REVIEW_REQUIRED,
        ),
    ],
)
def test_terminal_receipt_is_idempotent_and_survives_restart(
    tmp_path: Path,
    outcome: ReceiptOutcome,
    expected: RecoveryState,
) -> None:
    capability, event = _issued()
    config = load_backup_capability_recovery_config(CONFIG)
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        _, consumed_event = _consume(ledger)
        journal = RecoveryJournal(config, ledger)
        receipt = build_test_backup_execution_receipt(
            config,
            capability_id=capability.capability_id,
            consumption_event_id=consumed_event.event_id,
            test_executor_identity="test-executor",
            outcome=outcome,
            result_hash=HASH_B,
            recorded_at=NOW + timedelta(minutes=2),
        )
        assert journal.record(receipt) == receipt
        assert journal.record(receipt) == receipt
    with _ledger(tmp_path) as restarted:
        journal = RecoveryJournal(config, restarted)
        assert journal.load(capability.capability_id) == receipt
        assessment = journal.assess(
            capability.capability_id, assessed_at=NOW + timedelta(minutes=3)
        )
    assert assessment.state is expected
    assert assessment.receipt_id == receipt.receipt_id


def test_receipt_requires_exact_consumed_evidence(tmp_path: Path) -> None:
    capability, event = _issued()
    config = load_backup_capability_recovery_config(CONFIG)
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        journal = RecoveryJournal(config, ledger)
        receipt = build_test_backup_execution_receipt(
            config,
            capability_id=capability.capability_id,
            consumption_event_id="not-consumed",
            test_executor_identity="test-executor",
            outcome=ReceiptOutcome.SIMULATED_SUCCESS,
            result_hash=HASH_B,
            recorded_at=NOW + timedelta(minutes=2),
        )
        with pytest.raises(ValueError, match="exact consumed"):
            journal.record(receipt)
        _, consumed_event = _consume(ledger)
        wrong_executor = build_test_backup_execution_receipt(
            config,
            capability_id=capability.capability_id,
            consumption_event_id=consumed_event.event_id,
            test_executor_identity="wrong-executor",
            outcome=ReceiptOutcome.SIMULATED_SUCCESS,
            result_hash=HASH_B,
            recorded_at=NOW + timedelta(minutes=2),
        )
        with pytest.raises(ValueError, match="exact consumed"):
            journal.record(wrong_executor)
        valid = build_test_backup_execution_receipt(
            config,
            capability_id=capability.capability_id,
            consumption_event_id=consumed_event.event_id,
            test_executor_identity="test-executor",
            outcome=ReceiptOutcome.SIMULATED_SUCCESS,
            result_hash=HASH_B,
            recorded_at=NOW + timedelta(minutes=2),
        )
        with pytest.raises(ValueError, match="configuration binding"):
            journal.record(replace(valid, receipt_id="forged-receipt-id"))


def test_conflicting_terminal_receipt_fails_closed(tmp_path: Path) -> None:
    capability, event = _issued()
    config = load_backup_capability_recovery_config(CONFIG)
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        _, consumed_event = _consume(ledger)
        journal = RecoveryJournal(config, ledger)
        receipt = build_test_backup_execution_receipt(
            config,
            capability_id=capability.capability_id,
            consumption_event_id=consumed_event.event_id,
            test_executor_identity="test-executor",
            outcome=ReceiptOutcome.SIMULATED_SUCCESS,
            result_hash=HASH_B,
            recorded_at=NOW + timedelta(minutes=2),
        )
        journal.record(receipt)
        conflicting = build_test_backup_execution_receipt(
            config,
            capability_id=capability.capability_id,
            consumption_event_id=consumed_event.event_id,
            test_executor_identity="test-executor",
            outcome=ReceiptOutcome.SIMULATED_FAILURE,
            result_hash=HASH_B,
            recorded_at=NOW + timedelta(minutes=2),
        )
        with pytest.raises(ValueError, match="conflicts"):
            journal.record(conflicting)


def test_blocked_capability_remains_blocked_without_retry(tmp_path: Path) -> None:
    capability, event = _issued()
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        ledger.consume(
            capability.capability_id,
            certification_request_hash=HASH_B,
            test_executor_identity="test-executor",
            consumed_at=NOW + timedelta(minutes=1),
        )
        journal = RecoveryJournal(
            load_backup_capability_recovery_config(CONFIG), ledger
        )
        assessment = journal.assess(
            capability.capability_id, assessed_at=NOW + timedelta(minutes=2)
        )
    assert assessment.state is RecoveryState.BLOCKED
    assert not assessment.automatic_retry_authorized


def test_configuration_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["automatic_retry_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityRecoveryConfigError, match="authority"):
        load_backup_capability_recovery_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["missing_receipt_is_in_doubt"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityRecoveryConfigError, match="policy"):
        load_backup_capability_recovery_config(invalid)
