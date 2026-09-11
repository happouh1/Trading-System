from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop import (
    ProductionBackupReadinessAssessment,
    ProductionBackupReadinessCertificationAssessment,
    ProductionBackupReadinessCertificationRequest,
    ProductionBackupReadinessCertificationState,
    ProductionBackupReadinessState,
    build_production_backup_readiness_certification_request,
    consume_test_backup_capability,
    issue_test_backup_capability,
    load_backup_capability_rehearsal_config,
    load_backup_readiness_certification_config,
)
from trading_system.desktop.backup_capability_rehearsal import (
    BackupCapabilityRehearsalConfigError,
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
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9t.v1.yaml"
CERTIFICATION_CONFIG = ROOT / "config/desktop.phase9s.v1.yaml"
NOW = datetime(2026, 9, 11, 17, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
CONTROLS = (
    "ATOMIC_WRITE_DURABILITY_VERIFIED",
    "CRASH_RECOVERY_APPROVED",
    "ENCRYPTED_DESTINATION_APPROVED",
    "EXECUTOR_AUTHENTICATION_READY",
    "IDENTITY_REVOCATION_READY",
    "IMMUTABLE_AUDIT_STORE_READY",
    "KEY_CUSTODY_APPROVED",
    "REHEARSAL_INDEPENDENTLY_CERTIFIED",
    "RETENTION_POLICY_APPROVED",
    "TRUSTED_CLOCK_READY",
    "TRUSTED_NONCE_SERVICE_READY",
)


def _readiness() -> ProductionBackupReadinessAssessment:
    return ProductionBackupReadinessAssessment(
        "readiness-9r",
        ProductionBackupReadinessState.READY_FOR_EXECUTION_AUTHORIZATION_REVIEW,
        NOW - timedelta(minutes=20),
        "authorization-request-9p",
        HASH_A,
        "authorization-assessment-9p",
        "rehearsal-9q",
        CONTROLS,
        (),
        (),
        (),
        tuple(
            (control_id, f"sha256:{index:064x}")
            for index, control_id in enumerate(CONTROLS, start=1)
        ),
        HASH_B,
    )


def _evidence() -> tuple[
    ProductionBackupReadinessCertificationRequest,
    ProductionBackupReadinessCertificationAssessment,
]:
    request = build_production_backup_readiness_certification_request(
        load_backup_readiness_certification_config(CERTIFICATION_CONFIG),
        readiness=_readiness(),
        operator_nonce="phase9s-nonce",
        requested_at=NOW - timedelta(minutes=10),
        valid_from=NOW - timedelta(minutes=5),
        valid_until=NOW + timedelta(minutes=30),
        required_review_roles=("OPERATIONS_REVIEWER", "SECURITY_REVIEWER"),
    )
    assessment = ProductionBackupReadinessCertificationAssessment(
        "certification-assessment-9s",
        request.request_id,
        NOW - timedelta(minutes=1),
        ProductionBackupReadinessCertificationState.READINESS_CERTIFICATION_EVIDENCE_VERIFIED,
        request.required_review_roles,
        (),
        request.request_hash,
        request.config_hash,
    )
    return request, assessment


def _issue() -> tuple[
    ProductionBackupReadinessCertificationRequest,
    BackupCapability,
    BackupCapabilityEvent,
]:
    request, assessment = _evidence()
    capability, event = issue_test_backup_capability(
        load_backup_capability_rehearsal_config(CONFIG),
        certification_request=request,
        certification_assessment=assessment,
        test_executor_identity="test-only-backup-executor",
        test_nonce="phase9t-test-nonce",
        issued_at=NOW,
        valid_until=NOW + timedelta(minutes=10),
    )
    return request, capability, event


def test_issue_and_single_consumption_are_test_only() -> None:
    request, capability, issued = _issue()
    assert capability.state is CapabilityState.ISSUED
    assert issued.event_type is CapabilityEventType.ISSUED
    consumed, event = consume_test_backup_capability(
        capability,
        certification_request_hash=request.request_hash,
        test_executor_identity=capability.test_executor_identity,
        consumed_at=NOW + timedelta(minutes=1),
    )
    assert consumed.state is CapabilityState.CONSUMED
    assert event.event_type is CapabilityEventType.CONSUMED
    assert event.accepted
    assert not capability.production_capability
    assert not consumed.execution_authorized
    assert not event.operational_action_performed
    assert not event.backup_created
    assert not event.database_write_performed
    assert not event.network_used
    assert not event.broker_write_performed
    assert not event.live_trading_enabled


def test_replay_is_rejected_without_changing_consumed_state() -> None:
    request, capability, _ = _issue()
    consumed, _ = consume_test_backup_capability(
        capability,
        certification_request_hash=request.request_hash,
        test_executor_identity=capability.test_executor_identity,
        consumed_at=NOW + timedelta(minutes=1),
    )
    replayed, event = consume_test_backup_capability(
        consumed,
        certification_request_hash=request.request_hash,
        test_executor_identity=capability.test_executor_identity,
        consumed_at=NOW + timedelta(minutes=2),
    )
    assert replayed.state is CapabilityState.CONSUMED
    assert event.event_type is CapabilityEventType.REPLAY_REJECTED
    assert not event.accepted


def test_expired_capability_is_blocked() -> None:
    request, capability, _ = _issue()
    blocked, event = consume_test_backup_capability(
        capability,
        certification_request_hash=request.request_hash,
        test_executor_identity=capability.test_executor_identity,
        consumed_at=capability.valid_until,
    )
    assert blocked.state is CapabilityState.BLOCKED
    assert event.event_type is CapabilityEventType.EXPIRED_REJECTED


@pytest.mark.parametrize("mismatch", ["hash", "executor"])
def test_exact_binding_mismatch_is_blocked(mismatch: str) -> None:
    request, capability, _ = _issue()
    blocked, event = consume_test_backup_capability(
        capability,
        certification_request_hash=HASH_B if mismatch == "hash" else request.request_hash,
        test_executor_identity=(
            "wrong-executor"
            if mismatch == "executor"
            else capability.test_executor_identity
        ),
        consumed_at=NOW + timedelta(minutes=1),
    )
    assert blocked.state is CapabilityState.BLOCKED
    assert event.event_type is CapabilityEventType.BINDING_REJECTED


def test_unverified_or_mismatched_certification_is_rejected() -> None:
    request, assessment = _evidence()
    config = load_backup_capability_rehearsal_config(CONFIG)
    with pytest.raises(ValueError, match="verified"):
        issue_test_backup_capability(
            config,
            certification_request=request,
            certification_assessment=replace(
                assessment,
                state=ProductionBackupReadinessCertificationState.INCOMPLETE,
                reason_codes=("MISSING",),
            ),
            test_executor_identity="test-executor",
            test_nonce="nonce",
            issued_at=NOW,
            valid_until=NOW + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="binding"):
        issue_test_backup_capability(
            config,
            certification_request=request,
            certification_assessment=replace(assessment, request_id="wrong-request"),
            test_executor_identity="test-executor",
            test_nonce="nonce",
            issued_at=NOW,
            valid_until=NOW + timedelta(minutes=1),
        )


def test_config_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["production_capability_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityRehearsalConfigError, match="authority"):
        load_backup_capability_rehearsal_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["single_use"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupCapabilityRehearsalConfigError, match="policy"):
        load_backup_capability_rehearsal_config(invalid)


def test_issue_is_deterministic_and_canonical() -> None:
    first = _issue()
    second = _issue()
    assert first == second
    assert canonical_json(first) == canonical_json(second)
