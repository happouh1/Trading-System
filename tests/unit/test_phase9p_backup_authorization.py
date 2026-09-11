from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.desktop import (
    BackupAuthorizationAttestation,
    BackupAuthorizationEvidenceState,
    BackupAuthorizationRequest,
    RealDatabaseBackupManifest,
    RealDatabaseBackupManifestState,
    backup_authorization_message,
    build_backup_authorization_attestation,
    build_backup_authorization_request,
    build_database_upgrade_review_credential,
    evaluate_backup_authorization_evidence,
    load_backup_authorization_config,
)
from trading_system.desktop.backup_authorization import BackupAuthorizationConfigError
from trading_system.desktop.upgrade_authorization import DatabaseUpgradeReviewCredential
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9p.v1.yaml"
NOW = datetime(2026, 9, 10, 16, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _manifest() -> RealDatabaseBackupManifest:
    return RealDatabaseBackupManifest(
        "manifest-9o",
        RealDatabaseBackupManifestState.READY_FOR_AUTHORIZATION_REVIEW,
        NOW,
        "preflight-9n",
        HASH_A,
        "webull-sandbox.sqlite",
        HASH_B,
        8192,
        "backups/operator-db/webull-sandbox-bbbbbbbbbbbbbbbb.sqlite",
        "SQLITE_BACKUP_API_TO_EXCLUSIVE_NEW_FILE",
        (
            "SOURCE_HASH_BEFORE",
            "SQLITE_BACKUP_API",
            "SOURCE_HASH_AFTER",
            "TARGET_QUICK_CHECK",
            "TARGET_FOREIGN_KEY_CHECK",
            "TARGET_HASH_MATCH",
            "RESTORE_TEST",
        ),
        HASH_A,
        HASH_B,
        HASH_C,
        "operator-approved-backup-component",
        (),
        HASH_C,
    )


def _request() -> BackupAuthorizationRequest:
    return build_backup_authorization_request(
        load_backup_authorization_config(CONFIG),
        manifest=_manifest(),
        operator_nonce="operator-nonce-20260910-001",
        requested_at=NOW,
        valid_from=NOW + timedelta(minutes=5),
        valid_until=NOW + timedelta(minutes=35),
        required_review_roles=("SECURITY_REVIEWER", "OPERATIONS_REVIEWER"),
    )


def _signed(
    request: BackupAuthorizationRequest,
    *,
    same_principal: bool = False,
) -> tuple[
    tuple[DatabaseUpgradeReviewCredential, ...],
    tuple[BackupAuthorizationAttestation, ...],
]:
    credentials: list[DatabaseUpgradeReviewCredential] = []
    attestations: list[BackupAuthorizationAttestation] = []
    signed_at = NOW + timedelta(minutes=10)
    for role in request.required_review_roles:
        private = Ed25519PrivateKey.generate()
        credential = build_database_upgrade_review_credential(
            principal_id="same-principal" if same_principal else f"principal-{role}",
            role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=NOW,
            valid_until=NOW + timedelta(hours=2),
        )
        credentials.append(credential)
        attestations.append(
            build_backup_authorization_attestation(
                request,
                credential,
                signed_at=signed_at,
                signature=private.sign(
                    backup_authorization_message(request, credential, signed_at)
                ),
            )
        )
    return tuple(credentials), tuple(attestations)


def test_verified_evidence_never_grants_execution_authority() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    result = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials,
        attestations=tuple(reversed(attestations)),
        evaluated_at=NOW + timedelta(minutes=20),
    )
    assert result.state is BackupAuthorizationEvidenceState.BACKUP_AUTHORIZATION_EVIDENCE_VERIFIED
    assert not result.execution_authorized
    assert not result.backup_created
    assert not result.database_write_performed
    assert not result.network_used
    assert not result.broker_write_performed


def test_missing_invalid_and_expired_evidence_fail_closed() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    incomplete = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials[:1],
        attestations=attestations[:1],
        evaluated_at=NOW + timedelta(minutes=20),
    )
    assert incomplete.state is BackupAuthorizationEvidenceState.INCOMPLETE
    invalid = build_backup_authorization_attestation(
        request,
        credentials[0],
        signed_at=NOW + timedelta(minutes=10),
        signature=b"invalid",
    )
    blocked = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials,
        attestations=(invalid, attestations[1]),
        evaluated_at=NOW + timedelta(minutes=20),
    )
    assert blocked.state is BackupAuthorizationEvidenceState.BLOCKED
    expired = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(minutes=35),
    )
    assert expired.state is BackupAuthorizationEvidenceState.BLOCKED


def test_signatures_bind_exact_target_and_nonce() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    changed = replace(request, operator_nonce="different-nonce")
    result = evaluate_backup_authorization_evidence(
        changed,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(minutes=20),
    )
    assert result.state is BackupAuthorizationEvidenceState.BLOCKED
    assert "INVALID_ATTESTATION" in result.reason_codes


def test_same_principal_cannot_satisfy_two_roles() -> None:
    request = _request()
    credentials, attestations = _signed(request, same_principal=True)
    result = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(minutes=20),
    )
    assert result.state is BackupAuthorizationEvidenceState.BLOCKED
    assert "REVIEWER_SEPARATION_FAILURE" in result.reason_codes


def test_request_requires_ready_manifest_nonce_and_roles() -> None:
    config = load_backup_authorization_config(CONFIG)
    with pytest.raises(ValueError, match="review-ready"):
        build_backup_authorization_request(
            config,
            manifest=replace(
                _manifest(),
                state=RealDatabaseBackupManifestState.BLOCKED,
                blocker_codes=("BLOCKED",),
            ),
            operator_nonce="nonce",
            requested_at=NOW,
            valid_from=NOW + timedelta(minutes=1),
            valid_until=NOW + timedelta(minutes=2),
            required_review_roles=("REVIEWER",),
        )
    with pytest.raises(ValueError, match="nonce"):
        build_backup_authorization_request(
            config,
            manifest=_manifest(),
            operator_nonce=" ",
            requested_at=NOW,
            valid_from=NOW + timedelta(minutes=1),
            valid_until=NOW + timedelta(minutes=2),
            required_review_roles=("REVIEWER",),
        )


def test_config_weakening_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["execution_authority_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupAuthorizationConfigError, match="authority"):
        load_backup_authorization_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["distinct_reviewer_principals"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupAuthorizationConfigError, match="policy"):
        load_backup_authorization_config(invalid)


def test_assessment_is_deterministic_canonical_json() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    first = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(minutes=20),
    )
    second = evaluate_backup_authorization_evidence(
        request,
        credentials=credentials,
        attestations=tuple(reversed(attestations)),
        evaluated_at=NOW + timedelta(minutes=20),
    )
    assert first == second
    assert canonical_json(first) == canonical_json(second)
