from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.desktop import (
    ProductionBackupReadinessAssessment,
    ProductionBackupReadinessAttestation,
    ProductionBackupReadinessCertificationRequest,
    ProductionBackupReadinessCertificationState,
    ProductionBackupReadinessCredential,
    ProductionBackupReadinessState,
    build_production_backup_readiness_attestation,
    build_production_backup_readiness_certification_request,
    build_production_backup_readiness_credential,
    evaluate_production_backup_readiness_certification,
    load_backup_readiness_certification_config,
    production_backup_readiness_certification_message,
)
from trading_system.desktop.backup_certification import (
    BackupReadinessCertificationConfigError,
)
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9s.v1.yaml"
NOW = datetime(2026, 9, 11, 16, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
CONTROL_IDS = (
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
    evidence_hashes = tuple(
        (control_id, f"sha256:{index:064x}")
        for index, control_id in enumerate(CONTROL_IDS, start=1)
    )
    return ProductionBackupReadinessAssessment(
        "readiness-9r",
        ProductionBackupReadinessState.READY_FOR_EXECUTION_AUTHORIZATION_REVIEW,
        NOW - timedelta(minutes=10),
        "authorization-request-9p",
        HASH_A,
        "authorization-assessment-9p",
        "rehearsal-9q",
        CONTROL_IDS,
        (),
        (),
        (),
        evidence_hashes,
        HASH_B,
    )


def _request() -> ProductionBackupReadinessCertificationRequest:
    return build_production_backup_readiness_certification_request(
        load_backup_readiness_certification_config(CONFIG),
        readiness=_readiness(),
        operator_nonce="certification-nonce-20260911-001",
        requested_at=NOW - timedelta(minutes=5),
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=30),
        required_review_roles=("OPERATIONS_REVIEWER", "SECURITY_REVIEWER"),
    )


def _signed(
    request: ProductionBackupReadinessCertificationRequest,
    *,
    same_principal: bool = False,
) -> tuple[
    tuple[ProductionBackupReadinessCredential, ...],
    tuple[ProductionBackupReadinessAttestation, ...],
]:
    credentials: list[ProductionBackupReadinessCredential] = []
    attestations: list[ProductionBackupReadinessAttestation] = []
    for role in request.required_review_roles:
        private = Ed25519PrivateKey.generate()
        credential = build_production_backup_readiness_credential(
            principal_id="same-principal" if same_principal else f"principal-{role}",
            role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=NOW - timedelta(hours=1),
            valid_until=NOW + timedelta(hours=1),
        )
        credentials.append(credential)
        attestations.append(
            build_production_backup_readiness_attestation(
                request,
                credential,
                signed_at=NOW,
                signature=private.sign(
                    production_backup_readiness_certification_message(
                        request, credential, NOW
                    )
                ),
            )
        )
    return tuple(credentials), tuple(attestations)


def test_verified_certification_is_evidence_only() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    result = evaluate_production_backup_readiness_certification(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW,
    )
    assert (
        result.state
        is ProductionBackupReadinessCertificationState.READINESS_CERTIFICATION_EVIDENCE_VERIFIED
    )
    assert not result.execution_authorized
    assert not result.backup_created
    assert not result.database_write_performed
    assert not result.process_launched
    assert not result.network_used
    assert not result.credentials_loaded
    assert not result.broker_write_performed
    assert not result.sandbox_execution_enabled
    assert not result.live_trading_enabled


def test_missing_attestation_is_incomplete() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    result = evaluate_production_backup_readiness_certification(
        request,
        credentials=credentials[:1],
        attestations=attestations[:1],
        evaluated_at=NOW,
    )
    assert result.state is ProductionBackupReadinessCertificationState.INCOMPLETE
    assert result.reason_codes == ("REQUIRED_REVIEW_ATTESTATION_MISSING",)


def test_invalid_signature_and_changed_request_block() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    invalid = replace(attestations[0], signature_base64="aW52YWxpZA==")
    result = evaluate_production_backup_readiness_certification(
        request,
        credentials=credentials,
        attestations=(invalid, attestations[1]),
        evaluated_at=NOW,
    )
    assert result.state is ProductionBackupReadinessCertificationState.BLOCKED
    changed = replace(request, operator_nonce="changed-nonce")
    result = evaluate_production_backup_readiness_certification(
        changed,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW,
    )
    assert result.state is ProductionBackupReadinessCertificationState.BLOCKED


def test_same_principal_cannot_satisfy_distinct_roles() -> None:
    request = _request()
    credentials, attestations = _signed(request, same_principal=True)
    result = evaluate_production_backup_readiness_certification(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW,
    )
    assert result.state is ProductionBackupReadinessCertificationState.BLOCKED
    assert "REVIEWER_SEPARATION_FAILURE" in result.reason_codes


def test_expired_request_blocks() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    result = evaluate_production_backup_readiness_certification(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=request.valid_until,
    )
    assert result.state is ProductionBackupReadinessCertificationState.BLOCKED
    assert "OUTSIDE_CERTIFICATION_WINDOW" in result.reason_codes


def test_non_ready_matrix_and_empty_nonce_are_rejected() -> None:
    config = load_backup_readiness_certification_config(CONFIG)
    blocked = replace(
        _readiness(),
        state=ProductionBackupReadinessState.BLOCKED,
        blocker_codes=("BLOCKED",),
    )
    with pytest.raises(ValueError, match="review-ready"):
        build_production_backup_readiness_certification_request(
            config,
            readiness=blocked,
            operator_nonce="nonce",
            requested_at=NOW,
            valid_from=NOW,
            valid_until=NOW + timedelta(minutes=1),
            required_review_roles=("REVIEWER",),
        )
    with pytest.raises(ValueError, match="nonce"):
        build_production_backup_readiness_certification_request(
            config,
            readiness=_readiness(),
            operator_nonce=" ",
            requested_at=NOW,
            valid_from=NOW,
            valid_until=NOW + timedelta(minutes=1),
            required_review_roles=("REVIEWER",),
        )


def test_config_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["execution_authority_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupReadinessCertificationConfigError, match="authority"):
        load_backup_readiness_certification_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["distinct_reviewer_principals"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupReadinessCertificationConfigError, match="policy"):
        load_backup_readiness_certification_config(invalid)


def test_assessment_is_order_independent_and_canonical() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    first = evaluate_production_backup_readiness_certification(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW,
    )
    second = evaluate_production_backup_readiness_certification(
        request,
        credentials=tuple(reversed(credentials)),
        attestations=tuple(reversed(attestations)),
        evaluated_at=NOW,
    )
    assert first == second
    assert canonical_json(first) == canonical_json(second)
