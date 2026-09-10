from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.desktop import (
    DatabaseUpgradeReviewAttestation,
    DatabaseUpgradeReviewCredential,
    DatabaseUpgradeReviewRequest,
    DatabaseUpgradeReviewState,
    LocalSchemaUpgradePlan,
    UpgradeRehearsalResult,
    build_database_upgrade_review_attestation,
    build_database_upgrade_review_credential,
    build_database_upgrade_review_request,
    database_upgrade_review_message,
    evaluate_database_upgrade_review,
    load_database_upgrade_review_config,
)
from trading_system.desktop.upgrade_authorization import DatabaseUpgradeReviewConfigError
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9m.v1.yaml"
NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
HASH_D = "sha256:" + "d" * 64
REQUIRED = (
    "paper_burn_in_assessments",
    "paper_certification_assessments",
    "paper_operator_snapshots",
    "paper_rollout_gate_assessments",
    "paper_sandbox_lease_assessments",
    "paper_stage_authorization_assessments",
)


def _plan() -> LocalSchemaUpgradePlan:
    return LocalSchemaUpgradePlan(
        "upgrade-plan",
        "AVAILABLE",
        "REQUIRED",
        ("legacy_fixture",),
        REQUIRED,
        REQUIRED,
        ("ok",),
        HASH_A,
        HASH_B,
        True,
        HASH_C,
    )


def _rehearsal() -> UpgradeRehearsalResult:
    return UpgradeRehearsalResult(
        "rehearsal",
        "VERIFIED",
        "TEST_ONLY_LEGACY",
        HASH_A,
        HASH_A,
        HASH_B,
        HASH_C,
        HASH_B,
        ("legacy_fixture",),
        REQUIRED,
        (),
        (("legacy_fixture", 1),),
        ("ok",),
        ("ok",),
        0,
        0,
        ".upgrade-rehearsal/backup.sqlite",
        ".upgrade-rehearsal/upgraded.sqlite",
        ".upgrade-rehearsal/restored.sqlite",
        HASH_D,
    )


def _request() -> DatabaseUpgradeReviewRequest:
    return build_database_upgrade_review_request(
        load_database_upgrade_review_config(CONFIG),
        plan=_plan(),
        rehearsal=_rehearsal(),
        backup_policy_hash=HASH_A,
        recovery_procedure_hash=HASH_B,
        quiescence_procedure_hash=HASH_C,
        requested_at=NOW,
        maintenance_window_start=NOW + timedelta(hours=1),
        maintenance_window_end=NOW + timedelta(hours=2),
        required_review_roles=("SECURITY_REVIEWER", "OPERATIONS_REVIEWER"),
    )


def _signed(
    request: DatabaseUpgradeReviewRequest,
) -> tuple[
    tuple[DatabaseUpgradeReviewCredential, ...],
    tuple[DatabaseUpgradeReviewAttestation, ...],
]:
    credentials: list[DatabaseUpgradeReviewCredential] = []
    attestations: list[DatabaseUpgradeReviewAttestation] = []
    signed_at = NOW + timedelta(hours=1, minutes=5)
    for role in request.required_review_roles:
        private = Ed25519PrivateKey.generate()
        credential = build_database_upgrade_review_credential(
            principal_id=f"principal-{role}",
            role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=NOW,
            valid_until=NOW + timedelta(days=1),
        )
        signature = private.sign(
            database_upgrade_review_message(request, credential, signed_at)
        )
        credentials.append(credential)
        attestations.append(
            build_database_upgrade_review_attestation(
                request, credential, signed_at=signed_at, signature=signature
            )
        )
    return tuple(credentials), tuple(attestations)


def test_verified_review_evidence_never_authorizes_upgrade() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    assessment = evaluate_database_upgrade_review(
        request,
        credentials=credentials,
        attestations=tuple(reversed(attestations)),
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    assert assessment.state is DatabaseUpgradeReviewState.REVIEW_EVIDENCE_VERIFIED
    assert not assessment.real_backup_performed
    assert not assessment.real_migration_performed
    assert not assessment.restore_promoted
    assert not assessment.process_launched
    assert not assessment.network_used
    assert not assessment.broker_write_performed
    assert not assessment.live_trading_enabled


def test_missing_bad_and_out_of_window_reviews_fail_closed() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    incomplete = evaluate_database_upgrade_review(
        request,
        credentials=credentials[:1],
        attestations=attestations[:1],
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    assert incomplete.state is DatabaseUpgradeReviewState.INCOMPLETE
    bad = build_database_upgrade_review_attestation(
        request,
        credentials[0],
        signed_at=NOW + timedelta(hours=1, minutes=5),
        signature=b"invalid",
    )
    blocked = evaluate_database_upgrade_review(
        request,
        credentials=credentials,
        attestations=(bad, attestations[1]),
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    assert blocked.state is DatabaseUpgradeReviewState.BLOCKED
    expired = evaluate_database_upgrade_review(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(hours=2),
    )
    assert expired.state is DatabaseUpgradeReviewState.BLOCKED


def test_signatures_are_bound_to_exact_upgrade_package() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    changed = replace(request, source_hash=HASH_D)
    assessment = evaluate_database_upgrade_review(
        changed,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    assert assessment.state is DatabaseUpgradeReviewState.BLOCKED
    assert assessment.reason_codes == (
        "INVALID_ATTESTATION",
        "REQUIRED_REVIEW_ATTESTATION_MISSING",
    )


def test_same_principal_cannot_satisfy_two_review_roles() -> None:
    request = _request()
    credentials = []
    attestations = []
    signed_at = NOW + timedelta(hours=1, minutes=5)
    for role in request.required_review_roles:
        private = Ed25519PrivateKey.generate()
        credential = build_database_upgrade_review_credential(
            principal_id="same-principal",
            role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=NOW,
            valid_until=NOW + timedelta(days=1),
        )
        credentials.append(credential)
        attestations.append(
            build_database_upgrade_review_attestation(
                request,
                credential,
                signed_at=signed_at,
                signature=private.sign(
                    database_upgrade_review_message(request, credential, signed_at)
                ),
            )
        )
    assessment = evaluate_database_upgrade_review(
        request,
        credentials=tuple(credentials),
        attestations=tuple(attestations),
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    assert assessment.state is DatabaseUpgradeReviewState.BLOCKED
    assert "REVIEWER_SEPARATION_FAILURE" in assessment.reason_codes


def test_request_requires_required_plan_rehearsal_and_procedure_hashes() -> None:
    config = load_database_upgrade_review_config(CONFIG)
    with pytest.raises(ValueError, match="backup-required"):
        build_database_upgrade_review_request(
            config,
            plan=replace(
                _plan(), plan_status="NOT_REQUIRED", missing_tables=(), backup_required=False
            ),
            rehearsal=_rehearsal(),
            backup_policy_hash=HASH_A,
            recovery_procedure_hash=HASH_B,
            quiescence_procedure_hash=HASH_C,
            requested_at=NOW,
            maintenance_window_start=NOW + timedelta(hours=1),
            maintenance_window_end=NOW + timedelta(hours=2),
            required_review_roles=("REVIEWER",),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        build_database_upgrade_review_request(
            config,
            plan=_plan(),
            rehearsal=_rehearsal(),
            backup_policy_hash="unspecified",
            recovery_procedure_hash=HASH_B,
            quiescence_procedure_hash=HASH_C,
            requested_at=NOW,
            maintenance_window_start=NOW + timedelta(hours=1),
            maintenance_window_end=NOW + timedelta(hours=2),
            required_review_roles=("REVIEWER",),
        )


def test_config_rejects_policy_changes_and_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["require_phase9l_verified_rehearsal"] = False
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DatabaseUpgradeReviewConfigError, match="policy"):
        load_database_upgrade_review_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["real_backup_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DatabaseUpgradeReviewConfigError, match="authority"):
        load_database_upgrade_review_config(invalid)


def test_package_and_assessment_are_deterministic_canonical_json() -> None:
    request = _request()
    credentials, attestations = _signed(request)
    first = evaluate_database_upgrade_review(
        request,
        credentials=credentials,
        attestations=attestations,
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    second = evaluate_database_upgrade_review(
        request,
        credentials=credentials,
        attestations=tuple(reversed(attestations)),
        evaluated_at=NOW + timedelta(hours=1, minutes=30),
    )
    assert first == second
    assert canonical_json(first) == canonical_json(second)
