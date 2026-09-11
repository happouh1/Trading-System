from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.desktop import (
    RealDatabaseBackupManifest,
    RealDatabaseBackupManifestState,
    RealDatabaseBackupPreflight,
    RealDatabaseBackupPreflightState,
    build_real_database_backup_manifest,
    load_backup_manifest_config,
)
from trading_system.desktop.backup_manifest import BackupManifestConfigError
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9o.v1.yaml"
NOW = datetime(2026, 9, 10, 15, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
TARGET = "backups/operator-db/webull-sandbox-aaaaaaaaaaaaaaaa.sqlite"


def _preflight(
    state: RealDatabaseBackupPreflightState = (
        RealDatabaseBackupPreflightState.READY_FOR_BACKUP_REVIEW
    ),
    *,
    blockers: tuple[str, ...] = (),
    target_present: bool = False,
) -> RealDatabaseBackupPreflight:
    return RealDatabaseBackupPreflight(
        "preflight-9n",
        state,
        NOW,
        "request-9m",
        "assessment-9m",
        "webull-sandbox.sqlite",
        HASH_A,
        8192,
        "backups",
        "backups/operator-db",
        TARGET,
        1_048_576,
        True,
        ("ok",),
        0,
        (),
        HASH_B,
        target_present,
        blockers,
        HASH_C,
    )


def _manifest(preflight: RealDatabaseBackupPreflight) -> RealDatabaseBackupManifest:
    return build_real_database_backup_manifest(
        load_backup_manifest_config(CONFIG),
        preflight=preflight,
        encryption_policy_hash=HASH_A,
        retention_policy_hash=HASH_B,
        restore_test_policy_hash=HASH_C,
        execution_component_id="operator-approved-backup-component",
        created_at=NOW,
    )


def test_ready_manifest_binds_exact_preflight_without_authority() -> None:
    result = _manifest(_preflight())
    assert result.state is RealDatabaseBackupManifestState.READY_FOR_AUTHORIZATION_REVIEW
    assert result.target_path == TARGET
    assert result.backup_method == "SQLITE_BACKUP_API_TO_EXCLUSIVE_NEW_FILE"
    assert result.verification_steps[-1] == "RESTORE_TEST"
    assert not result.backup_authorized
    assert not result.backup_created
    assert not result.database_write_performed
    assert not result.network_used
    assert not result.broker_write_performed


def test_blocked_preflight_propagates_all_reasons() -> None:
    result = _manifest(
        _preflight(
            RealDatabaseBackupPreflightState.BLOCKED,
            blockers=("SOURCE_HASH_MISMATCH",),
        )
    )
    assert result.state is RealDatabaseBackupManifestState.BLOCKED
    assert result.blocker_codes == (
        "PHASE9N_PREFLIGHT_BLOCKED",
        "SOURCE_HASH_MISMATCH",
    )


def test_identical_existing_backup_requires_review() -> None:
    result = _manifest(
        _preflight(
            RealDatabaseBackupPreflightState.BACKUP_ALREADY_PRESENT,
            target_present=True,
        )
    )
    assert result.state is RealDatabaseBackupManifestState.EXISTING_BACKUP_REVIEW_REQUIRED
    assert not result.backup_authorized


def test_missing_or_non_content_addressed_target_blocks() -> None:
    missing = _manifest(replace(_preflight(), target_path=None))
    assert missing.blocker_codes == ("TARGET_PATH_UNAVAILABLE",)
    wrong = _manifest(replace(_preflight(), target_path="backups/operator-db/manual.sqlite"))
    assert wrong.blocker_codes == ("TARGET_NOT_CONTENT_ADDRESSED",)


def test_operator_policy_hashes_component_and_time_are_required() -> None:
    config = load_backup_manifest_config(CONFIG)
    with pytest.raises(ValueError, match="SHA-256"):
        build_real_database_backup_manifest(
            config,
            preflight=_preflight(),
            encryption_policy_hash="unspecified",
            retention_policy_hash=HASH_B,
            restore_test_policy_hash=HASH_C,
            execution_component_id="component",
            created_at=NOW,
        )
    with pytest.raises(ValueError, match="component"):
        build_real_database_backup_manifest(
            config,
            preflight=_preflight(),
            encryption_policy_hash=HASH_A,
            retention_policy_hash=HASH_B,
            restore_test_policy_hash=HASH_C,
            execution_component_id=" ",
            created_at=NOW,
        )
    with pytest.raises(ValueError, match="UTC"):
        build_real_database_backup_manifest(
            config,
            preflight=_preflight(),
            encryption_policy_hash=HASH_A,
            retention_policy_hash=HASH_B,
            restore_test_policy_hash=HASH_C,
            execution_component_id="component",
            created_at=datetime(2026, 9, 10, 15),
        )


def test_config_weakening_and_procedure_changes_fail_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["backup_authorization_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupManifestConfigError, match="authority"):
        load_backup_manifest_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["verification_steps"].pop()
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BackupManifestConfigError, match="procedure"):
        load_backup_manifest_config(invalid)


def test_manifest_is_deterministic_canonical_json() -> None:
    first = _manifest(_preflight())
    second = _manifest(_preflight())
    assert first == second
    assert canonical_json(first) == canonical_json(second)
