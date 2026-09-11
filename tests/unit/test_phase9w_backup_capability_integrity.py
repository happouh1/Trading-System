from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop.backup_capability_integrity import (
    BackupCapabilityIntegrityConfigError,
    audit_test_backup_capability_ledger,
    load_backup_capability_integrity_config,
)
from trading_system.desktop.backup_capability_integrity import (
    TestBackupLedgerIntegrityAssessment as IntegrityAssessment,
)
from trading_system.desktop.backup_capability_integrity import (
    TestBackupLedgerIntegrityState as IntegrityState,
)
from trading_system.desktop.backup_capability_ledger import (
    TestOnlyBackupCapabilityLedger as CapabilityLedger,
)
from trading_system.desktop.backup_capability_ledger import (
    bind_backup_capability_config_hash,
    load_backup_capability_ledger_config,
)
from trading_system.desktop.backup_capability_recovery import (
    TestBackupReceiptOutcome as ReceiptOutcome,
)
from trading_system.desktop.backup_capability_recovery import (
    TestOnlyBackupRecoveryJournal as RecoveryJournal,
)
from trading_system.desktop.backup_capability_recovery import (
    build_test_backup_execution_receipt,
    load_backup_capability_recovery_config,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityEventType as CapabilityEventType,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestBackupCapabilityState as CapabilityState,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestOnlyBackupCapability as Capability,
)
from trading_system.desktop.backup_capability_rehearsal import (
    TestOnlyBackupCapabilityEvent as CapabilityEvent,
)
from trading_system.desktop.backup_capability_rehearsal import (
    load_backup_capability_rehearsal_config,
)
from trading_system.serialization import deterministic_id

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9w.v1.yaml"
RECOVERY_CONFIG = ROOT / "config/desktop.phase9v.v1.yaml"
LEDGER_CONFIG = ROOT / "config/desktop.phase9u.v1.yaml"
CAPABILITY_CONFIG = ROOT / "config/desktop.phase9t.v1.yaml"
DATABASE = ".p9u-capability-ledger/phase9w.sqlite"
NOW = datetime(2026, 9, 11, 18, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _ledger(tmp_path: Path) -> CapabilityLedger:
    capability_config = load_backup_capability_rehearsal_config(CAPABILITY_CONFIG)
    config = bind_backup_capability_config_hash(
        load_backup_capability_ledger_config(LEDGER_CONFIG), capability_config.config_hash
    )
    return CapabilityLedger(config, project_root=tmp_path, database_path=DATABASE)


def _evidence() -> tuple[Capability, CapabilityEvent]:
    config_hash = load_backup_capability_rehearsal_config(CAPABILITY_CONFIG).config_hash
    assessment_id = "phase9s-assessment"
    request_id = "phase9s-request"
    executor = "test-executor"
    nonce = "phase9w-nonce"
    valid_until = NOW + timedelta(minutes=10)
    capability_id = deterministic_id(
        "test_backup_capability",
        (assessment_id, request_id, HASH_A, executor, nonce, NOW, valid_until, config_hash),
    )
    capability = Capability(
        capability_id,
        assessment_id,
        request_id,
        HASH_A,
        executor,
        nonce,
        NOW,
        valid_until,
        CapabilityState.ISSUED,
        config_hash,
    )
    reason = "TEST_CAPABILITY_ISSUED"
    event_id = deterministic_id(
        "test_backup_capability_event",
        (
            capability_id,
            CapabilityEventType.ISSUED,
            NOW,
            None,
            CapabilityState.ISSUED,
            reason,
            HASH_A,
            config_hash,
        ),
    )
    return capability, CapabilityEvent(
        event_id,
        capability_id,
        CapabilityEventType.ISSUED,
        NOW,
        None,
        CapabilityState.ISSUED,
        True,
        reason,
        HASH_A,
        config_hash,
    )


def _audit(
    ledger: CapabilityLedger,
    recovery: RecoveryJournal,
    capability_id: str,
) -> IntegrityAssessment:
    return audit_test_backup_capability_ledger(
        load_backup_capability_integrity_config(CONFIG),
        ledger=ledger,
        recovery=recovery,
        capability_id=capability_id,
        assessed_at=NOW + timedelta(minutes=3),
    )


def test_valid_issued_and_consumed_ledgers_verify(tmp_path: Path) -> None:
    capability, event = _evidence()
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        recovery = RecoveryJournal(load_backup_capability_recovery_config(RECOVERY_CONFIG), ledger)
        issued = _audit(ledger, recovery, capability.capability_id)
        ledger.consume(
            capability.capability_id,
            certification_request_hash=HASH_A,
            test_executor_identity="test-executor",
            consumed_at=NOW + timedelta(minutes=1),
        )
        consumed = _audit(ledger, recovery, capability.capability_id)
    assert issued.state is IntegrityState.INTEGRITY_VERIFIED
    assert consumed.state is IntegrityState.INTEGRITY_VERIFIED
    assert not consumed.repair_performed
    assert not consumed.production_action_authorized


def test_valid_receipt_verifies_across_restart(tmp_path: Path) -> None:
    capability, event = _evidence()
    recovery_config = load_backup_capability_recovery_config(RECOVERY_CONFIG)
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        _, consumed = ledger.consume(
            capability.capability_id,
            certification_request_hash=HASH_A,
            test_executor_identity="test-executor",
            consumed_at=NOW + timedelta(minutes=1),
        )
        recovery = RecoveryJournal(recovery_config, ledger)
        recovery.record(
            build_test_backup_execution_receipt(
                recovery_config,
                capability_id=capability.capability_id,
                consumption_event_id=consumed.event_id,
                test_executor_identity="test-executor",
                outcome=ReceiptOutcome.SIMULATED_SUCCESS,
                result_hash=HASH_B,
                recorded_at=NOW + timedelta(minutes=2),
            )
        )
    with _ledger(tmp_path) as restarted:
        recovery = RecoveryJournal(recovery_config, restarted)
        assessment = _audit(restarted, recovery, capability.capability_id)
    assert assessment.state is IntegrityState.INTEGRITY_VERIFIED


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        (
            "UPDATE test_backup_capabilities SET certification_request_hash = ?",
            "CAPABILITY_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE test_backup_capability_events SET reason_code = 'TAMPERED'",
            "EVENT_IDENTITY_MISMATCH",
        ),
        (
            "UPDATE test_backup_capability_events SET sequence = 3",
            "EVENT_SEQUENCE_INVALID",
        ),
    ],
)
def test_capability_event_and_sequence_tampering_fail_closed(
    tmp_path: Path, statement: str, reason: str
) -> None:
    capability, event = _evidence()
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        recovery = RecoveryJournal(load_backup_capability_recovery_config(RECOVERY_CONFIG), ledger)
        parameters = (HASH_B,) if "?" in statement else ()
        ledger.connection.execute(statement, parameters)
        assessment = _audit(ledger, recovery, capability.capability_id)
    assert assessment.state is IntegrityState.INTEGRITY_FAILED
    assert reason in assessment.reasons


def test_missing_capability_and_noncausal_time_fail_closed(tmp_path: Path) -> None:
    capability, event = _evidence()
    with _ledger(tmp_path) as ledger:
        ledger.register(capability, event)
        recovery = RecoveryJournal(load_backup_capability_recovery_config(RECOVERY_CONFIG), ledger)
        missing = _audit(ledger, recovery, "missing-capability")
        with pytest.raises(ValueError, match="causal"):
            audit_test_backup_capability_ledger(
                load_backup_capability_integrity_config(CONFIG),
                ledger=ledger,
                recovery=recovery,
                capability_id=capability.capability_id,
                assessed_at=NOW - timedelta(seconds=1),
            )
    assert missing.state is IntegrityState.INTEGRITY_FAILED
    assert missing.reasons == ("CAPABILITY_MISSING",)


def test_configuration_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["repair_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityIntegrityConfigError, match="authority"):
        load_backup_capability_integrity_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["tampering_fails_closed"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityIntegrityConfigError, match="policy"):
        load_backup_capability_integrity_config(invalid)
