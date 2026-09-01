from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6c import CONFIG as AUDIT_CONFIG
from tests.unit.test_phase6c import seed_reconciliation
from trading_system.operations import (
    AuditExportVerificationStatus,
    ObservationAuditExportConfigError,
    ObservationAuditExportRegistry,
    ObservationAuditExportService,
    ObservationAuditRegistry,
    load_observation_audit_config,
    load_observation_audit_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6d.v1.yaml"


def seed_packet(repository: SQLiteRepository) -> str:
    _, _, reconciliation = seed_reconciliation(repository)
    registry = ObservationAuditRegistry(
        repository, load_observation_audit_config(AUDIT_CONFIG)
    )
    packet = registry.create(
        reconciliation_id=reconciliation.reconciliation_id,
        created_at=AS_OF + timedelta(hours=4),
        source_revision="sha256:phase6d-source-packet",
    )
    assert registry.insert(packet) is True
    return packet.packet_id


def test_phase6d_config_rejects_authority_thresholds_and_paths(tmp_path: Path) -> None:
    config = load_observation_audit_export_config(CONFIG)
    assert config.export_directory == "observation_audit_exports"
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["signing_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditExportConfigError, match="unsigned offline"):
        load_observation_audit_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["promotion_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditExportConfigError, match="cannot invent"):
        load_observation_audit_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["export"]["directory"] = "../outside"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditExportConfigError, match="controls are mandatory"):
        load_observation_audit_export_config(invalid)


def test_export_is_canonical_content_addressed_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_observation_audit_export_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        packet_id = seed_packet(repository)
        registry = ObservationAuditExportRegistry(repository, config)
        service = ObservationAuditExportService(config, registry)
        first = service.export(
            packet_id=packet_id,
            exported_at=AS_OF + timedelta(hours=5),
            source_revision="sha256:phase6d-export",
        )
        repeated = service.export(
            packet_id=packet_id,
            exported_at=AS_OF + timedelta(hours=5),
            source_revision="sha256:phase6d-export",
        )
        later = service.export(
            packet_id=packet_id,
            exported_at=AS_OF + timedelta(hours=6),
            source_revision="sha256:phase6d-export-later",
        )
        assert first == repeated
        assert first.export_id != later.export_id
        assert first.artifact_path == later.artifact_path
        assert first.artifact_hash == later.artifact_hash
        assert first.reconciliation_status == "MATCHED"
        assert first.campaign_status == "INCOMPLETE"
    artifact = tmp_path / first.artifact_path
    data = artifact.read_bytes()
    assert len(data) == first.artifact_bytes
    assert json.dumps(json.loads(data), sort_keys=True, separators=(",", ":")).encode() == data
    with SQLiteRepository(database) as repository:
        repository.migrate()
        loaded = ObservationAuditExportRegistry(repository, config).manifest(first.export_id)
    assert loaded == first


def test_verify_success_and_tamper_are_append_only(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_observation_audit_export_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        packet_id = seed_packet(repository)
        registry = ObservationAuditExportRegistry(repository, config)
        service = ObservationAuditExportService(config, registry)
        manifest = service.export(
            packet_id=packet_id,
            exported_at=AS_OF + timedelta(hours=5),
            source_revision="sha256:export",
        )
        verified = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=6),
            source_revision="sha256:verify-good",
        )
        assert verified.status is AuditExportVerificationStatus.VERIFIED
        assert verified.reasons == ()
        artifact = tmp_path / manifest.artifact_path
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        failed = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=7),
            source_revision="sha256:verify-tampered",
        )
        assert failed.status is AuditExportVerificationStatus.FAILED
        assert "EXPORT_FILE_HASH_MISMATCH" in failed.reasons
        _, latest, count = registry.status(manifest.export_id)
    assert latest == "FAILED"
    assert count == 2


def test_export_rejects_tampered_source_and_future_timestamp(tmp_path: Path) -> None:
    config = load_observation_audit_export_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        packet_id = seed_packet(repository)
        service = ObservationAuditExportService(
            config, ObservationAuditExportRegistry(repository, config)
        )
        with pytest.raises(ValueError, match="cannot predate"):
            service.export(
                packet_id=packet_id,
                exported_at=AS_OF + timedelta(hours=3),
                source_revision="sha256:too-early",
            )
        repository.connection.execute(
            """UPDATE operations_observation_audit_artifacts SET payload_json = ?
               WHERE packet_id = ? AND artifact_name =
                     (SELECT MIN(artifact_name) FROM operations_observation_audit_artifacts
                      WHERE packet_id = ?)""",
            ('{"tampered":true}', packet_id, packet_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="source artifact payload is corrupt"):
            service.export(
                packet_id=packet_id,
                exported_at=AS_OF + timedelta(hours=5),
                source_revision="sha256:tampered",
            )


def test_verification_rejects_unsafe_persisted_path_without_reading_outside(
    tmp_path: Path,
) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_observation_audit_export_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        packet_id = seed_packet(repository)
        registry = ObservationAuditExportRegistry(repository, config)
        service = ObservationAuditExportService(config, registry)
        manifest = service.export(
            packet_id=packet_id,
            exported_at=AS_OF + timedelta(hours=5),
            source_revision="sha256:path-export",
        )
        row = repository.connection.execute(
            "SELECT payload_json FROM operations_observation_audit_exports WHERE export_id = ?",
            (manifest.export_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[0]))
        payload["artifact_path"] = "../outside.json"
        from trading_system.serialization import canonical_hash, canonical_json

        repository.connection.execute(
            """UPDATE operations_observation_audit_exports
               SET payload_json = ?, payload_hash = ? WHERE export_id = ?""",
            (canonical_json(payload), canonical_hash(payload), manifest.export_id),
        )
        repository.connection.commit()
        verification = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=6),
            source_revision="sha256:path-verify",
        )
    assert verification.status is AuditExportVerificationStatus.FAILED
    assert verification.reasons == ("EXPORT_PATH_UNSAFE",)


def test_root_and_packaged_phase6d_migrations_match() -> None:
    root = ROOT / "migrations" / "031_phase_6d_observation_audit_exports.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "031_phase_6d_observation_audit_exports.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
