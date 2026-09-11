from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.desktop import (
    AuthorizedBackupRehearsalResult,
    BackupAuthorizationAssessment,
    BackupAuthorizationEvidenceState,
    BackupAuthorizationRequest,
    ProductionBackupControlEvidence,
    ProductionBackupControlState,
    ProductionBackupReadinessAssessment,
    ProductionBackupReadinessState,
    assess_production_backup_readiness,
    load_backup_readiness_config,
)
from trading_system.desktop.backup_readiness import BackupReadinessConfigError
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9r.v1.yaml"
NOW = datetime(2026, 9, 11, 15, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _request() -> BackupAuthorizationRequest:
    return BackupAuthorizationRequest(
        "request-9p",
        "manifest-9o",
        HASH_A,
        "preflight-9n",
        HASH_B,
        HASH_C,
        "backups/operator-db/database.sqlite",
        "approved-backup-component",
        "operator-nonce",
        NOW - timedelta(minutes=10),
        NOW - timedelta(minutes=5),
        NOW + timedelta(minutes=30),
        ("OPERATIONS_REVIEWER", "SECURITY_REVIEWER"),
        HASH_A,
        HASH_B,
    )


def _authorization(request: BackupAuthorizationRequest) -> BackupAuthorizationAssessment:
    return BackupAuthorizationAssessment(
        "assessment-9p",
        request.request_id,
        NOW - timedelta(minutes=1),
        BackupAuthorizationEvidenceState.BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED,
        request.required_review_roles,
        (),
        request.request_hash,
        request.config_hash,
    )


def _rehearsal(request: BackupAuthorizationRequest) -> AuthorizedBackupRehearsalResult:
    return AuthorizedBackupRehearsalResult(
        "rehearsal-9q",
        "VERIFIED",
        request.request_id,
        request.manifest_id,
        "TEST_ONLY_READINESS_FIXTURE",
        "fixtures/backup-authorization-rehearsal/legacy.sqlite",
        HASH_A,
        HASH_A,
        HASH_A,
        HASH_A,
        HASH_B,
        (("example", 1),),
        ("ok",),
        ("ok",),
        0,
        0,
        ".p9q-backup-rehearsal/backup.sqlite",
        ".p9q-backup-rehearsal/restored.sqlite",
        False,
        HASH_C,
    )


def _controls() -> tuple[ProductionBackupControlEvidence, ...]:
    config = load_backup_readiness_config(CONFIG)
    values = config.values["required_controls"]
    assert isinstance(values, tuple)
    return tuple(
        ProductionBackupControlEvidence(
            str(control_id),
            ProductionBackupControlState.VERIFIED,
            f"sha256:{index:064x}",
            f"reviewer-{index}",
            NOW - timedelta(hours=1),
            NOW + timedelta(hours=1),
        )
        for index, control_id in enumerate(values, start=1)
    )


def _assess(
    controls: tuple[ProductionBackupControlEvidence, ...],
    *,
    request: BackupAuthorizationRequest | None = None,
    authorization: BackupAuthorizationAssessment | None = None,
    rehearsal: AuthorizedBackupRehearsalResult | None = None,
) -> ProductionBackupReadinessAssessment:
    bound_request = request or _request()
    return assess_production_backup_readiness(
        load_backup_readiness_config(CONFIG),
        request=bound_request,
        authorization_assessment=authorization or _authorization(bound_request),
        rehearsal=rehearsal or _rehearsal(bound_request),
        control_evidence=controls,
        evaluated_at=NOW,
    )


def test_all_controls_reach_review_only_without_execution_authority() -> None:
    result = _assess(_controls())
    assert result.state is ProductionBackupReadinessState.READY_FOR_EXECUTION_AUTHORIZATION_REVIEW
    assert not result.execution_authorized
    assert not result.backup_created
    assert not result.database_write_performed
    assert not result.process_launched
    assert not result.network_used
    assert not result.credentials_loaded
    assert not result.broker_write_performed
    assert not result.sandbox_execution_enabled
    assert not result.live_trading_enabled


def test_missing_control_is_not_ready() -> None:
    controls = _controls()
    result = _assess(controls[:-1])
    assert result.state is ProductionBackupReadinessState.NOT_READY
    assert result.missing_controls == (controls[-1].control_id,)


def test_unverified_control_is_not_ready() -> None:
    controls = _controls()
    changed = replace(controls[0], state=ProductionBackupControlState.UNVERIFIED)
    result = _assess((changed, *controls[1:]))
    assert result.state is ProductionBackupReadinessState.NOT_READY
    assert result.unverified_controls == (controls[0].control_id,)


def test_expired_control_blocks() -> None:
    controls = _controls()
    expired = replace(
        controls[0],
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW,
    )
    result = _assess((expired, *controls[1:]))
    assert result.state is ProductionBackupReadinessState.BLOCKED
    assert result.blocker_codes == (f"EXPIRED_CONTROL:{controls[0].control_id}",)


def test_phase9p_and_phase9q_request_mismatches_block() -> None:
    request = _request()
    result = _assess(
        _controls(),
        request=request,
        authorization=replace(_authorization(request), request_id="wrong-request"),
        rehearsal=replace(_rehearsal(request), request_id="wrong-request"),
    )
    assert result.state is ProductionBackupReadinessState.BLOCKED
    assert result.blocker_codes == (
        "PHASE9P_REQUEST_MISMATCH",
        "PHASE9Q_REQUEST_MISMATCH",
    )


def test_duplicate_or_unknown_control_evidence_is_rejected() -> None:
    controls = _controls()
    with pytest.raises(ValueError, match="unique"):
        _assess((*controls, controls[0]))
    unknown = replace(controls[0], control_id="UNRECOGNIZED_CONTROL")
    with pytest.raises(ValueError, match="unknown"):
        _assess((unknown, *controls[1:]))


def test_config_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["backup_creation_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupReadinessConfigError, match="authority"):
        load_backup_readiness_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["require_exact_request_binding"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupReadinessConfigError, match="policy"):
        load_backup_readiness_config(invalid)


def test_assessment_is_order_independent_and_canonical() -> None:
    controls = _controls()
    first = _assess(controls)
    second = _assess(tuple(reversed(controls)))
    assert first == second
    assert canonical_json(first) == canonical_json(second)
