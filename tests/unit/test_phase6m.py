from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6l import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6l import seed_verified_chain
from trading_system.operations import (
    ProspectiveChainReviewBundleConfigError,
    ProspectiveChainReviewBundleRegistry,
    ProspectiveChainReviewBundleService,
    ProspectiveChainReviewRegistry,
    ProspectiveChainReviewVerdict,
    ProspectiveReviewBundleVerificationStatus,
    load_prospective_chain_review_bundle_config,
    load_prospective_chain_review_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6m.v1.yaml"


def seed_review_history(repository: SQLiteRepository) -> tuple[str, str]:
    export_id, verification_id = seed_verified_chain(repository)
    registry = ProspectiveChainReviewRegistry(
        repository, load_prospective_chain_review_config(REVIEW_CONFIG)
    )
    first = registry.create(
        export_id=export_id,
        verification_id=verification_id,
        reviewer_id="asserted-reviewer-1",
        reviewed_at=AS_OF + timedelta(hours=14),
        verdict=ProspectiveChainReviewVerdict.PARTIAL,
        reason_codes=("FOLLOW_UP",),
        notes="initial",
        supersedes_review_id=None,
        source_revision="sha256:phase6m-review-1",
    )
    assert registry.insert(first)
    second = registry.create(
        export_id=export_id,
        verification_id=verification_id,
        reviewer_id="asserted-reviewer-1",
        reviewed_at=AS_OF + timedelta(hours=15),
        verdict=ProspectiveChainReviewVerdict.CONFIRMED,
        reason_codes=("FOLLOW_UP_COMPLETE",),
        notes="replacement",
        supersedes_review_id=first.review_id,
        source_revision="sha256:phase6m-review-2",
    )
    assert registry.insert(second)
    return export_id, verification_id


def bundle_service(repository: SQLiteRepository) -> ProspectiveChainReviewBundleService:
    config = load_prospective_chain_review_bundle_config(CONFIG)
    return ProspectiveChainReviewBundleService(
        config, ProspectiveChainReviewBundleRegistry(repository, config)
    )


def test_phase6m_config_rejects_authority_thresholds_and_paths(tmp_path: Path) -> None:
    assert (
        load_prospective_chain_review_bundle_config(CONFIG).export_directory
        == "prospective_chain_review_bundles"
    )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["signing_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewBundleConfigError, match="unsigned offline"):
        load_prospective_chain_review_bundle_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["consensus_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewBundleConfigError, match="cannot invent"):
        load_prospective_chain_review_bundle_config(invalid)


def test_bundle_is_canonical_complete_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_prospective_chain_review_bundle_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
        service = bundle_service(repository)
        manifest = service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=16),
            source_revision="sha256:phase6m-bundle",
        )
        assert service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=16),
            source_revision="sha256:phase6m-bundle",
        ) == manifest
        assert (manifest.review_count, manifest.active_review_count) == (2, 1)
    data = (tmp_path / manifest.artifact_path).read_bytes()
    assert json.dumps(json.loads(data), sort_keys=True, separators=(",", ":")).encode() == data
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert ProspectiveChainReviewBundleRegistry(repository, config).manifest(
            manifest.bundle_id
        ) == manifest


def test_bundle_verification_records_success_and_tamper(tmp_path: Path) -> None:
    config = load_prospective_chain_review_bundle_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
        service = bundle_service(repository)
        manifest = service.export(
            export_id=export_id,
            source_verification_id=verification_id,
            bundled_at=AS_OF + timedelta(hours=16),
            source_revision="sha256:bundle",
        )
        verified = service.verify(
            bundle_id=manifest.bundle_id,
            verified_at=AS_OF + timedelta(hours=17),
            source_revision="sha256:verify",
        )
        assert verified.status is ProspectiveReviewBundleVerificationStatus.VERIFIED
        artifact = tmp_path / manifest.artifact_path
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        failed = service.verify(
            bundle_id=manifest.bundle_id,
            verified_at=AS_OF + timedelta(hours=18),
            source_revision="sha256:tampered",
        )
        assert failed.status is ProspectiveReviewBundleVerificationStatus.FAILED
        assert "PROSPECTIVE_REVIEW_BUNDLE_HASH_MISMATCH" in failed.reasons
        _, latest, count = ProspectiveChainReviewBundleRegistry(repository, config).status(
            manifest.bundle_id
        )
    assert (latest, count) == ("FAILED", 2)


def test_bundle_requires_reviews_and_causal_time(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_verified_chain(repository)
        with pytest.raises(ValueError, match="at least one review"):
            bundle_service(repository).export(
                export_id=export_id,
                source_verification_id=verification_id,
                bundled_at=AS_OF + timedelta(hours=16),
                source_revision="sha256:empty",
            )
        review_registry = ProspectiveChainReviewRegistry(
            repository, load_prospective_chain_review_config(REVIEW_CONFIG)
        )
        review = review_registry.create(
            export_id=export_id,
            verification_id=verification_id,
            reviewer_id="asserted-reviewer",
            reviewed_at=AS_OF + timedelta(hours=14),
            verdict=ProspectiveChainReviewVerdict.CONFIRMED,
            reason_codes=(),
            notes="",
            supersedes_review_id=None,
            source_revision="sha256:causal-review",
        )
        assert review_registry.insert(review)
        with pytest.raises(ValueError, match="cannot predate"):
            bundle_service(repository).export(
                export_id=export_id,
                source_verification_id=verification_id,
                bundled_at=AS_OF + timedelta(hours=13, minutes=30),
                source_revision="sha256:early",
            )


def test_bundle_rejects_corrupt_review_payload(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
        repository.connection.execute(
            """UPDATE operations_prospective_chain_reviews SET payload_json = ?
               WHERE export_id = ?""",
            ('{"tampered":true}', export_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="source prospective review is corrupt"):
            bundle_service(repository).export(
                export_id=export_id,
                source_verification_id=verification_id,
                bundled_at=AS_OF + timedelta(hours=16),
                source_revision="sha256:corrupt",
            )


def test_phase6m_migration_copies_match() -> None:
    root = ROOT / "migrations" / "040_phase_6m_prospective_chain_review_bundles.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
