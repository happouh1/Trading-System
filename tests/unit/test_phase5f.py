from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system import PACKAGE_VERSION
from trading_system.operations import (
    OperationsReleaseConfigError,
    OperationsReleaseRegistry,
    ReleaseEvidenceBundle,
    ReleaseEvidenceStatus,
    load_operations_release_config,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5f.v1.yaml"
AS_OF = datetime(2026, 8, 30, 16, tzinfo=UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _payload(name: str) -> tuple[str, str]:
    payload = {"evidence": name, "schema_version": "test.1"}
    return canonical_json(payload), canonical_hash(payload)


def seed_release_chain(repository: SQLiteRepository, *, as_of: datetime = AS_OF) -> None:
    timestamp = _timestamp(as_of - timedelta(minutes=1))
    payload_json, payload_hash = _payload("readiness")
    connection = repository.connection
    connection.execute(
        "INSERT INTO operations_manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "manifest-1",
            timestamp,
            "READY",
            "sha256:readiness-config",
            PACKAGE_VERSION,
            "sha256:readiness-source",
            payload_json,
            payload_hash,
        ),
    )
    schedule_json, schedule_hash = _payload("schedule")
    connection.execute(
        "INSERT INTO operations_schedules VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "job-1",
            "offline-shadow",
            "shadow",
            "OFFLINE",
            timestamp,
            3600,
            "sha256:monitor-config",
            schedule_json,
            schedule_hash,
        ),
    )
    plan_json, plan_hash = _payload("plan")
    connection.execute(
        "INSERT INTO operations_schedule_plans VALUES (?, ?, ?, ?, ?)",
        ("plan-1", timestamp, "sha256:monitor-config", plan_json, plan_hash),
    )
    monitor_json, monitor_hash = _payload("monitor")
    connection.execute(
        "INSERT INTO operations_monitor_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "monitor-1",
            timestamp,
            "READY",
            "plan-1",
            "sha256:monitor-source",
            "sha256:monitor-config",
            monitor_json,
            monitor_hash,
        ),
    )
    request_json, request_hash = _payload("request")
    connection.execute(
        "INSERT INTO operations_run_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "request-1",
            "plan-1",
            "job-1",
            timestamp,
            timestamp,
            "RUN_OFFLINE_SHADOW",
            None,
            "sha256:runner-source",
            "sha256:runner-config",
            request_json,
            request_hash,
        ),
    )
    attempt_json, attempt_hash = _payload("attempt")
    connection.execute(
        """INSERT INTO operations_run_attempts
           (attempt_id, request_id, attempt_number, started_at, finished_at, status,
            exit_code, result_json, stdout_hash, stderr_hash, next_retry_at, config_hash,
            payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "attempt-1",
            "request-1",
            1,
            timestamp,
            timestamp,
            "SUCCEEDED",
            0,
            "{}",
            "sha256:stdout",
            "sha256:stderr",
            None,
            "sha256:runner-config",
            attempt_json,
            attempt_hash,
        ),
    )
    control_json, control_hash = _payload("control")
    connection.execute(
        "INSERT INTO operations_control_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "control-1",
            timestamp,
            "request-1",
            "READY",
            "sha256:control-config",
            control_json,
            control_hash,
        ),
    )
    backup_json, backup_hash = _payload("backup")
    connection.execute(
        "INSERT INTO operations_backup_manifests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "backup-1",
            timestamp,
            "source.sqlite",
            "backups/source.sqlite",
            "sha256:artifact",
            100,
            "sha256:backup-source",
            PACKAGE_VERSION,
            "sha256:resilience-config",
            backup_json,
            backup_hash,
        ),
    )
    restore_json, restore_hash = _payload("restore")
    connection.execute(
        "INSERT INTO operations_restore_verifications VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "restore-1",
            "backup-1",
            timestamp,
            "restore/source.sqlite",
            "VERIFIED",
            "sha256:resilience-config",
            restore_json,
            restore_hash,
        ),
    )
    connection.commit()


def _evaluate(
    repository: SQLiteRepository, *, as_of: datetime = AS_OF
) -> ReleaseEvidenceBundle:
    config = load_operations_release_config(CONFIG)
    return OperationsReleaseRegistry(repository, config).evaluate(
        as_of=as_of,
        readiness_manifest_id="manifest-1",
        monitor_report_id="monitor-1",
        control_snapshot_id="control-1",
        run_request_id="request-1",
        backup_id="backup-1",
        restore_verification_id="restore-1",
        source_revision="sha256:release-source",
    )


def test_phase5f_config_is_offline_evidence_only_and_fail_closed(tmp_path: Path) -> None:
    config = load_operations_release_config(CONFIG)
    assert dict(config.required_statuses)["run_attempt"] == "SUCCEEDED"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["production_readiness_claim_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsReleaseConfigError, match="offline evidence only"):
        load_operations_release_config(invalid)


def test_complete_release_bundle_is_deterministic_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        seed_release_chain(repository)
        config = load_operations_release_config(CONFIG)
        registry = OperationsReleaseRegistry(repository, config)
        first = _evaluate(repository)
        assert first.status is ReleaseEvidenceStatus.COMPLETE
        assert first.reasons == ()
        assert registry.insert(first) is True
        assert registry.insert(first) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        second = _evaluate(repository)
        status, payload = OperationsReleaseRegistry(
            repository, load_operations_release_config(CONFIG)
        ).status(first.bundle_id)
    assert second == first
    assert status == "COMPLETE"
    assert json.loads(payload)["bundle_id"] == first.bundle_id
    assert "NOT_A_PRODUCTION_READINESS_CLAIM" in first.disclosures


def test_missing_and_inconsistent_evidence_is_explicitly_incomplete(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        seed_release_chain(repository)
        repository.connection.execute(
            "UPDATE operations_control_snapshots SET request_id = NULL WHERE snapshot_id = ?",
            ("control-1",),
        )
        repository.connection.execute(
            "DELETE FROM operations_restore_verifications WHERE verification_id = ?",
            ("restore-1",),
        )
        repository.connection.commit()
        bundle = _evaluate(repository)
    assert bundle.status is ReleaseEvidenceStatus.INCOMPLETE
    assert "CONTROL_SNAPSHOT_REQUEST_MISMATCH" in bundle.reasons
    assert "RESTORE_VERIFICATION_MISSING" in bundle.reasons


def test_future_and_tampered_evidence_is_rejected(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        seed_release_chain(repository)
        repository.connection.execute(
            "UPDATE operations_monitor_reports SET as_of = ? WHERE report_id = ?",
            (_timestamp(AS_OF + timedelta(seconds=1)), "monitor-1"),
        )
        repository.connection.execute(
            "UPDATE operations_backup_manifests SET payload_json = ? WHERE backup_id = ?",
            ('{"tampered":true}', "backup-1"),
        )
        repository.connection.commit()
        bundle = _evaluate(repository)
    assert bundle.status is ReleaseEvidenceStatus.INCOMPLETE
    assert "MONITOR_REPORT_FUTURE_EVIDENCE" in bundle.reasons
    assert "BACKUP_MANIFEST_PAYLOAD_HASH_MISMATCH" in bundle.reasons


def test_root_and_packaged_phase5f_migrations_match() -> None:
    root = ROOT / "migrations" / "027_phase_5f_release_evidence.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "027_phase_5f_release_evidence.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
