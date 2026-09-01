from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6e import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6e import seed_verified_export
from trading_system.operations import (
    AuditReviewVerdict,
    ObservationAuditReviewExportConfigError,
    ObservationAuditReviewExportRegistry,
    ObservationAuditReviewExportService,
    ObservationAuditReviewRegistry,
    ReviewBundleVerificationStatus,
    load_observation_audit_review_config,
    load_observation_audit_review_export_config,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6f.v1.yaml"


def seed_review_history(repository: SQLiteRepository) -> tuple[str, str]:
    export_id, verification = seed_verified_export(repository)
    registry = ObservationAuditReviewRegistry(
        repository, load_observation_audit_review_config(REVIEW_CONFIG)
    )
    first = registry.create(
        export_id=export_id,
        verification_id=verification.verification_id,
        reviewer_id="reviewer-assertion-1",
        reviewed_at=AS_OF + timedelta(hours=7),
        verdict=AuditReviewVerdict.PARTIAL,
        reason_codes=("FOLLOW_UP",),
        notes="initial",
        supersedes_review_id=None,
        source_revision="sha256:phase6f-review-1",
    )
    assert registry.insert(first) is True
    second = registry.create(
        export_id=export_id,
        verification_id=verification.verification_id,
        reviewer_id="reviewer-assertion-1",
        reviewed_at=AS_OF + timedelta(hours=8),
        verdict=AuditReviewVerdict.CONFIRMED,
        reason_codes=("FOLLOW_UP_COMPLETE",),
        notes="replacement",
        supersedes_review_id=first.review_id,
        source_revision="sha256:phase6f-review-2",
    )
    assert registry.insert(second) is True
    return export_id, verification.verification_id


def test_phase6f_config_rejects_authority_thresholds_and_paths(tmp_path: Path) -> None:
    config = load_observation_audit_review_export_config(CONFIG)
    assert config.export_directory == "observation_audit_review_bundles"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["signing_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewExportConfigError, match="unsigned offline"):
        load_observation_audit_review_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["consensus_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewExportConfigError, match="cannot invent"):
        load_observation_audit_review_export_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["export"]["directory"] = "../outside"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewExportConfigError, match="controls are mandatory"):
        load_observation_audit_review_export_config(invalid)


def test_review_bundle_is_canonical_complete_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_observation_audit_review_export_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
        registry = ObservationAuditReviewExportRegistry(repository, config)
        service = ObservationAuditReviewExportService(config, registry)
        first = service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=9),
            source_revision="sha256:phase6f-bundle",
        )
        repeated = service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=9),
            source_revision="sha256:phase6f-bundle",
        )
        assert first == repeated
        assert first.review_count == 2
        assert first.active_review_count == 1
        assert first.summary_eligible_count == 1
    data = (tmp_path / first.artifact_path).read_bytes()
    assert json.dumps(json.loads(data), sort_keys=True, separators=(",", ":")).encode() == data
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert ObservationAuditReviewExportRegistry(repository, config).manifest(
            first.bundle_id
        ) == first


def test_review_bundle_verification_records_success_and_tamper(tmp_path: Path) -> None:
    config = load_observation_audit_review_export_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
        registry = ObservationAuditReviewExportRegistry(repository, config)
        service = ObservationAuditReviewExportService(config, registry)
        manifest = service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=9),
            source_revision="sha256:bundle",
        )
        verified = service.verify(
            bundle_id=manifest.bundle_id,
            verified_at=AS_OF + timedelta(hours=10),
            source_revision="sha256:verify",
        )
        assert verified.status is ReviewBundleVerificationStatus.VERIFIED
        artifact = tmp_path / manifest.artifact_path
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        failed = service.verify(
            bundle_id=manifest.bundle_id,
            verified_at=AS_OF + timedelta(hours=11),
            source_revision="sha256:tampered",
        )
        assert failed.status is ReviewBundleVerificationStatus.FAILED
        assert "REVIEW_BUNDLE_HASH_MISMATCH" in failed.reasons
        _, latest, count = registry.status(manifest.bundle_id)
    assert latest == "FAILED"
    assert count == 2


def test_review_bundle_rejects_no_reviews_future_time_and_tamper(tmp_path: Path) -> None:
    config = load_observation_audit_review_export_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification = seed_verified_export(repository)
        service = ObservationAuditReviewExportService(
            config, ObservationAuditReviewExportRegistry(repository, config)
        )
        with pytest.raises(ValueError, match="at least one review"):
            service.export(
                export_id=export_id,
                source_verification_id=verification.verification_id,
                bundled_at=AS_OF + timedelta(hours=9),
                source_revision="sha256:empty",
            )
        review_registry = ObservationAuditReviewRegistry(
            repository, load_observation_audit_review_config(REVIEW_CONFIG)
        )
        review = review_registry.create(
            export_id=export_id,
            verification_id=verification.verification_id,
            reviewer_id="reviewer",
            reviewed_at=AS_OF + timedelta(hours=8),
            verdict=AuditReviewVerdict.UNCERTAIN,
            reason_codes=("UNKNOWN",),
            notes="",
            supersedes_review_id=None,
            source_revision="sha256:review",
        )
        assert review_registry.insert(review) is True
        with pytest.raises(ValueError, match="cannot predate"):
            service.export(
                export_id=export_id,
                source_verification_id=verification.verification_id,
                bundled_at=AS_OF + timedelta(hours=7),
                source_revision="sha256:early",
            )
        repository.connection.execute(
            """UPDATE operations_observation_audit_reviews SET payload_json = ?
               WHERE review_id = ?""",
            ('{"tampered":true}', review.review_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="source audit review is corrupt"):
            service.export(
                export_id=export_id,
                source_verification_id=verification.verification_id,
                bundled_at=AS_OF + timedelta(hours=9),
                source_revision="sha256:corrupt",
            )


def test_review_bundle_verification_rejects_unsafe_persisted_path(tmp_path: Path) -> None:
    config = load_observation_audit_review_export_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
        registry = ObservationAuditReviewExportRegistry(repository, config)
        service = ObservationAuditReviewExportService(config, registry)
        manifest = service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=9),
            source_revision="sha256:path-bundle",
        )
        row = repository.connection.execute(
            """SELECT payload_json FROM operations_observation_audit_review_bundles
               WHERE bundle_id = ?""",
            (manifest.bundle_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row[0]))
        payload["artifact_path"] = "../outside.json"
        repository.connection.execute(
            """UPDATE operations_observation_audit_review_bundles
               SET payload_json = ?, payload_hash = ? WHERE bundle_id = ?""",
            (canonical_json(payload), canonical_hash(payload), manifest.bundle_id),
        )
        repository.connection.commit()
        verification = service.verify(
            bundle_id=manifest.bundle_id,
            verified_at=AS_OF + timedelta(hours=10),
            source_revision="sha256:path-verify",
        )
    assert verification.status is ReviewBundleVerificationStatus.FAILED
    assert verification.reasons == ("REVIEW_BUNDLE_PATH_UNSAFE",)


def test_root_and_packaged_phase6f_migrations_match() -> None:
    root = ROOT / "migrations" / "033_phase_6f_observation_audit_review_bundles.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "033_phase_6f_observation_audit_review_bundles.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
