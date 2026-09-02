from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6k import export_service, seed_materialization
from trading_system.operations import (
    ProspectiveChainReviewConfigError,
    ProspectiveChainReviewRegistry,
    ProspectiveChainReviewVerdict,
    load_prospective_chain_review_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6l.v1.yaml"


def seed_verified_chain(repository: SQLiteRepository) -> tuple[str, str]:
    service = export_service(repository)
    manifest = service.export(
        materialization_id=seed_materialization(repository),
        exported_at=AS_OF + timedelta(hours=12),
        source_revision="sha256:phase6l-export",
    )
    verification = service.verify(
        export_id=manifest.export_id,
        verified_at=AS_OF + timedelta(hours=13),
        source_revision="sha256:phase6l-verification",
    )
    return manifest.export_id, verification.verification_id


def test_phase6l_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_prospective_chain_review_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["reviewer_authentication_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewConfigError, match="no authority"):
        load_prospective_chain_review_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["consensus_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewConfigError, match="cannot invent"):
        load_prospective_chain_review_config(invalid)


def test_review_is_canonical_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_prospective_chain_review_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = seed_verified_chain(repository)
        registry = ProspectiveChainReviewRegistry(repository, config)
        review = registry.create(
            export_id=export_id,
            verification_id=verification_id,
            reviewer_id="asserted-reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=14),
            verdict=ProspectiveChainReviewVerdict.CONFIRMED,
            reason_codes=("CHAIN_REVIEWED", "HASHES_CHECKED", "CHAIN_REVIEWED"),
            notes="Offline independent assertion.",
            supersedes_review_id=None,
            source_revision="sha256:phase6l-review",
        )
        assert review.reason_codes == ("CHAIN_REVIEWED", "HASHES_CHECKED")
        assert review.reviewer_authenticated is False
        assert review.promoted is False
        assert registry.insert(review) is True
        assert registry.insert(review) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        reviews, counts = ProspectiveChainReviewRegistry(repository, config).status(export_id)
    assert reviews[0]["review_id"] == review.review_id
    assert counts["CONFIRMED"] == 1
    assert counts["SUMMARY_ELIGIBLE"] == 1


def test_uncertain_supersession_remains_explicit(tmp_path: Path) -> None:
    config = load_prospective_chain_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_verified_chain(repository)
        registry = ProspectiveChainReviewRegistry(repository, config)
        first = registry.create(
            export_id=export_id,
            verification_id=verification_id,
            reviewer_id="asserted-reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=14),
            verdict=ProspectiveChainReviewVerdict.PARTIAL,
            reason_codes=("FOLLOW_UP_REQUIRED",),
            notes="",
            supersedes_review_id=None,
            source_revision="sha256:first",
        )
        assert registry.insert(first)
        replacement = registry.create(
            export_id=export_id,
            verification_id=verification_id,
            reviewer_id="asserted-reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=15),
            verdict=ProspectiveChainReviewVerdict.UNCERTAIN,
            reason_codes=("INSUFFICIENT_CONTEXT",),
            notes="",
            supersedes_review_id=first.review_id,
            source_revision="sha256:replacement",
        )
        assert registry.insert(replacement)
        _, counts = registry.status(export_id)
    assert counts["TOTAL"] == 2
    assert counts["ACTIVE"] == 1
    assert counts["PARTIAL"] == 0
    assert counts["UNCERTAIN"] == 1
    assert counts["SUMMARY_ELIGIBLE"] == 0


def test_review_rejects_failed_or_tampered_verification(tmp_path: Path) -> None:
    config = load_prospective_chain_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        service = export_service(repository)
        manifest = service.export(
            materialization_id=seed_materialization(repository),
            exported_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:tamper-export",
        )
        artifact = repository.path.resolve().parent / manifest.artifact_path
        artifact.write_bytes(b"{}")
        failed = service.verify(
            export_id=manifest.export_id,
            verified_at=AS_OF + timedelta(hours=13),
            source_revision="sha256:failed",
        )
        with pytest.raises(ValueError, match="requires a VERIFIED export"):
            ProspectiveChainReviewRegistry(repository, config).create(
                export_id=manifest.export_id,
                verification_id=failed.verification_id,
                reviewer_id="asserted-reviewer-1",
                reviewed_at=AS_OF + timedelta(hours=14),
                verdict=ProspectiveChainReviewVerdict.REJECTED,
                reason_codes=("CORRUPT_ARTIFACT",),
                notes="",
                supersedes_review_id=None,
                source_revision="sha256:rejected",
            )


def test_review_timestamp_and_supersession_are_causal(tmp_path: Path) -> None:
    config = load_prospective_chain_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_verified_chain(repository)
        registry = ProspectiveChainReviewRegistry(repository, config)
        with pytest.raises(ValueError, match="cannot predate"):
            registry.create(
                export_id=export_id,
                verification_id=verification_id,
                reviewer_id="asserted-reviewer-1",
                reviewed_at=AS_OF + timedelta(hours=12),
                verdict=ProspectiveChainReviewVerdict.CONFIRMED,
                reason_codes=(),
                notes="",
                supersedes_review_id=None,
                source_revision="sha256:early",
            )
        first = registry.create(
            export_id=export_id,
            verification_id=verification_id,
            reviewer_id="asserted-reviewer-1",
            reviewed_at=AS_OF + timedelta(hours=14),
            verdict=ProspectiveChainReviewVerdict.CONFIRMED,
            reason_codes=(),
            notes="",
            supersedes_review_id=None,
            source_revision="sha256:first",
        )
        assert registry.insert(first)
        with pytest.raises(ValueError, match="same export and reviewer"):
            registry.create(
                export_id=export_id,
                verification_id=verification_id,
                reviewer_id="asserted-reviewer-2",
                reviewed_at=AS_OF + timedelta(hours=15),
                verdict=ProspectiveChainReviewVerdict.REJECTED,
                reason_codes=(),
                notes="",
                supersedes_review_id=first.review_id,
                source_revision="sha256:wrong-reviewer",
            )


def test_review_rejects_corrupt_verification_payload(tmp_path: Path) -> None:
    config = load_prospective_chain_review_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = seed_verified_chain(repository)
        repository.connection.execute(
            """UPDATE operations_prospective_chain_export_verifications
               SET payload_json = ? WHERE verification_id = ?""",
            ('{"tampered":true}', verification_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="verification payload is corrupt"):
            ProspectiveChainReviewRegistry(repository, config).create(
                export_id=export_id,
                verification_id=verification_id,
                reviewer_id="asserted-reviewer-1",
                reviewed_at=AS_OF + timedelta(hours=14),
                verdict=ProspectiveChainReviewVerdict.REJECTED,
                reason_codes=("CORRUPT",),
                notes="",
                supersedes_review_id=None,
                source_revision="sha256:corrupt",
            )


def test_phase6l_migration_copies_match() -> None:
    root = ROOT / "migrations" / "039_phase_6l_prospective_chain_reviews.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
