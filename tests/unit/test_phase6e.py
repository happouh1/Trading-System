from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6d import CONFIG as EXPORT_CONFIG
from tests.unit.test_phase6d import seed_packet
from trading_system.operations import (
    AuditExportVerification,
    AuditReviewVerdict,
    ObservationAuditExportRegistry,
    ObservationAuditExportService,
    ObservationAuditReviewConfigError,
    ObservationAuditReviewRegistry,
    load_observation_audit_export_config,
    load_observation_audit_review_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6e.v1.yaml"


def seed_verified_export(
    repository: SQLiteRepository,
) -> tuple[str, AuditExportVerification]:
    packet_id = seed_packet(repository)
    export_config = load_observation_audit_export_config(EXPORT_CONFIG)
    registry = ObservationAuditExportRegistry(repository, export_config)
    service = ObservationAuditExportService(export_config, registry)
    manifest = service.export(
        packet_id=packet_id,
        exported_at=AS_OF + timedelta(hours=5),
        source_revision="sha256:phase6e-export",
    )
    verification = service.verify(
        export_id=manifest.export_id,
        verified_at=AS_OF + timedelta(hours=6),
        source_revision="sha256:phase6e-verification",
    )
    return manifest.export_id, verification


def test_phase6e_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    config = load_observation_audit_review_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["reviewer_authentication_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewConfigError, match="no authority"):
        load_observation_audit_review_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["consensus_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewConfigError, match="cannot invent"):
        load_observation_audit_review_config(invalid)


def test_review_is_canonical_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_observation_audit_review_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification = seed_verified_export(repository)
        registry = ObservationAuditReviewRegistry(repository, config)
        review = registry.create(
            export_id=export_id,
            verification_id=verification.verification_id,
            reviewer_id="reviewer-assertion-1",
            reviewed_at=AS_OF + timedelta(hours=7),
            verdict=AuditReviewVerdict.CONFIRMED,
            reason_codes=("INTEGRITY_CHECKED", "CHAIN_REVIEWED", "INTEGRITY_CHECKED"),
            notes="Offline evidence review only.",
            supersedes_review_id=None,
            source_revision="sha256:phase6e-review",
        )
        assert review.reason_codes == ("CHAIN_REVIEWED", "INTEGRITY_CHECKED")
        assert review.eligible_for_summary is True
        assert review.reviewer_authenticated is False
        assert review.promoted is False
        assert registry.insert(review) is True
        assert registry.insert(review) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        reviews, counts = ObservationAuditReviewRegistry(repository, config).status(export_id)
    assert len(reviews) == 1
    assert reviews[0]["review_id"] == review.review_id
    assert counts["CONFIRMED"] == 1
    assert counts["SUMMARY_ELIGIBLE"] == 1


def test_uncertain_supersession_remains_explicit_without_consensus(tmp_path: Path) -> None:
    config = load_observation_audit_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification = seed_verified_export(repository)
        registry = ObservationAuditReviewRegistry(repository, config)
        first = registry.create(
            export_id=export_id,
            verification_id=verification.verification_id,
            reviewer_id="reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=7),
            verdict=AuditReviewVerdict.PARTIAL,
            reason_codes=("FOLLOW_UP_REQUIRED",),
            notes="",
            supersedes_review_id=None,
            source_revision="sha256:first-review",
        )
        assert registry.insert(first) is True
        replacement = registry.create(
            export_id=export_id,
            verification_id=verification.verification_id,
            reviewer_id="reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=8),
            verdict=AuditReviewVerdict.UNCERTAIN,
            reason_codes=("INSUFFICIENT_REVIEW_CONTEXT",),
            notes="",
            supersedes_review_id=first.review_id,
            source_revision="sha256:replacement-review",
        )
        assert replacement.eligible_for_summary is False
        assert registry.insert(replacement) is True
        reviews, counts = registry.status(export_id)
    assert len(reviews) == 2
    assert counts["TOTAL"] == 2
    assert counts["ACTIVE"] == 1
    assert counts["PARTIAL"] == 0
    assert counts["UNCERTAIN"] == 1
    assert counts["SUMMARY_ELIGIBLE"] == 0


def test_review_rejects_failed_verification(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    review_config = load_observation_audit_review_config(CONFIG)
    export_config = load_observation_audit_export_config(EXPORT_CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, good_verification = seed_verified_export(repository)
        manifest = ObservationAuditExportRegistry(repository, export_config).manifest(export_id)
        artifact = tmp_path / manifest.artifact_path
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        failed = ObservationAuditExportService(
            export_config, ObservationAuditExportRegistry(repository, export_config)
        ).verify(
            export_id=export_id,
            verified_at=AS_OF + timedelta(hours=7),
            source_revision="sha256:failed-verification",
        )
        registry = ObservationAuditReviewRegistry(repository, review_config)
        with pytest.raises(ValueError, match="requires a VERIFIED export"):
            registry.create(
                export_id=export_id,
                verification_id=failed.verification_id,
                reviewer_id="reviewer-1",
                reviewed_at=AS_OF + timedelta(hours=8),
                verdict=AuditReviewVerdict.REJECTED,
                reason_codes=("TAMPERED",),
                notes="",
                supersedes_review_id=None,
                source_revision="sha256:failed-review",
            )
        assert good_verification.verification_id != failed.verification_id


def test_review_timestamp_and_supersession_links_are_causal(tmp_path: Path) -> None:
    config = load_observation_audit_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification = seed_verified_export(repository)
        registry = ObservationAuditReviewRegistry(repository, config)
        with pytest.raises(ValueError, match="cannot predate"):
            registry.create(
                export_id=export_id,
                verification_id=verification.verification_id,
                reviewer_id="reviewer-1",
                reviewed_at=AS_OF + timedelta(hours=5),
                verdict=AuditReviewVerdict.CONFIRMED,
                reason_codes=(),
                notes="",
                supersedes_review_id=None,
                source_revision="sha256:early-review",
            )
        first = registry.create(
            export_id=export_id,
            verification_id=verification.verification_id,
            reviewer_id="reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=7),
            verdict=AuditReviewVerdict.CONFIRMED,
            reason_codes=(),
            notes="",
            supersedes_review_id=None,
            source_revision="sha256:first",
        )
        assert registry.insert(first) is True
        with pytest.raises(ValueError, match="same export and reviewer"):
            registry.create(
                export_id=export_id,
                verification_id=verification.verification_id,
                reviewer_id="reviewer-2",
                reviewed_at=AS_OF + timedelta(hours=8),
                verdict=AuditReviewVerdict.REJECTED,
                reason_codes=(),
                notes="",
                supersedes_review_id=first.review_id,
                source_revision="sha256:wrong-reviewer",
            )


def test_review_rejects_tampered_verification_payload(tmp_path: Path) -> None:
    config = load_observation_audit_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification = seed_verified_export(repository)
        repository.connection.execute(
            """UPDATE operations_observation_audit_export_verifications
               SET payload_json = ? WHERE verification_id = ?""",
            ('{"tampered":true}', verification.verification_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="verification payload is corrupt"):
            ObservationAuditReviewRegistry(repository, config).create(
                export_id=export_id,
                verification_id=verification.verification_id,
                reviewer_id="reviewer-1",
                reviewed_at=AS_OF + timedelta(hours=7),
                verdict=AuditReviewVerdict.REJECTED,
                reason_codes=("CORRUPT",),
                notes="",
                supersedes_review_id=None,
                source_revision="sha256:tamper-review",
            )


def test_root_and_packaged_phase6e_migrations_match() -> None:
    root = ROOT / "migrations" / "032_phase_6e_observation_audit_reviews.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "032_phase_6e_observation_audit_reviews.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
