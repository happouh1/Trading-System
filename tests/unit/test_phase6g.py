from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6f import CONFIG as BUNDLE_CONFIG
from tests.unit.test_phase6f import seed_review_history
from trading_system.operations import (
    ObservationAuditReviewCatalogConfigError,
    ObservationAuditReviewCatalogRegistry,
    ObservationAuditReviewExportRegistry,
    ObservationAuditReviewExportService,
    ReviewBundleVerification,
    load_observation_audit_review_catalog_config,
    load_observation_audit_review_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6g.v1.yaml"


def seed_verified_bundle(
    repository: SQLiteRepository,
) -> tuple[str, ReviewBundleVerification]:
    export_id, source_verification_id = seed_review_history(repository)
    config = load_observation_audit_review_export_config(BUNDLE_CONFIG)
    registry = ObservationAuditReviewExportRegistry(repository, config)
    service = ObservationAuditReviewExportService(config, registry)
    manifest = service.export(
        export_id=export_id,
        source_verification_id=source_verification_id,
        bundled_at=AS_OF + timedelta(hours=9),
        source_revision="sha256:phase6g-bundle",
    )
    verification = service.verify(
        bundle_id=manifest.bundle_id,
        verified_at=AS_OF + timedelta(hours=10),
        source_revision="sha256:phase6g-bundle-verification",
    )
    return manifest.bundle_id, verification


def test_phase6g_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    config = load_observation_audit_review_catalog_config(CONFIG)
    assert config.source_directory == "observation_audit_review_bundles"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["consensus_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewCatalogConfigError, match="no authority"):
        load_observation_audit_review_catalog_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_bundle_count_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ObservationAuditReviewCatalogConfigError, match="cannot invent"):
        load_observation_audit_review_catalog_config(invalid)


def test_catalog_is_canonical_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_observation_audit_review_catalog_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
        registry = ObservationAuditReviewCatalogRegistry(repository, config)
        catalog = registry.create(
            catalog_name="explicit-review-catalog",
            cataloged_at=AS_OF + timedelta(hours=11),
            sources=((bundle_id, verification.verification_id),),
            source_revision="sha256:phase6g-catalog",
        )
        assert catalog.bundle_count == 1
        assert catalog.total_review_count == 2
        assert catalog.total_active_review_count == 1
        assert catalog.total_summary_eligible_count == 1
        assert registry.insert(catalog) is True
        assert registry.insert(catalog) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        loaded = ObservationAuditReviewCatalogRegistry(repository, config).status(
            catalog.catalog_id
        )
    assert loaded == catalog


def test_catalog_normalizes_source_order(tmp_path: Path) -> None:
    config = load_observation_audit_review_catalog_config(CONFIG)
    bundle_config = load_observation_audit_review_export_config(BUNDLE_CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, source_verification_id = seed_review_history(repository)
        bundle_registry = ObservationAuditReviewExportRegistry(repository, bundle_config)
        service = ObservationAuditReviewExportService(bundle_config, bundle_registry)
        first = service.export(
            export_id=export_id,
            source_verification_id=source_verification_id,
            bundled_at=AS_OF + timedelta(hours=9),
            source_revision="sha256:first-bundle",
        )
        first_verification = service.verify(
            bundle_id=first.bundle_id,
            verified_at=AS_OF + timedelta(hours=10),
            source_revision="sha256:first-verify",
        )
        second = service.export(
            export_id=export_id,
            source_verification_id=source_verification_id,
            bundled_at=AS_OF + timedelta(hours=10),
            source_revision="sha256:second-bundle",
        )
        second_verification = service.verify(
            bundle_id=second.bundle_id,
            verified_at=AS_OF + timedelta(hours=11),
            source_revision="sha256:second-verify",
        )
        registry = ObservationAuditReviewCatalogRegistry(repository, config)
        forward = registry.create(
            catalog_name="ordered",
            cataloged_at=AS_OF + timedelta(hours=12),
            sources=(
                (first.bundle_id, first_verification.verification_id),
                (second.bundle_id, second_verification.verification_id),
            ),
            source_revision="sha256:catalog",
        )
        reverse = registry.create(
            catalog_name="ordered",
            cataloged_at=AS_OF + timedelta(hours=12),
            sources=(
                (second.bundle_id, second_verification.verification_id),
                (first.bundle_id, first_verification.verification_id),
            ),
            source_revision="sha256:catalog",
        )
    assert forward == reverse


def test_catalog_rejects_duplicates_future_time_and_tampered_file(tmp_path: Path) -> None:
    config = load_observation_audit_review_catalog_config(CONFIG)
    bundle_config = load_observation_audit_review_export_config(BUNDLE_CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
        registry = ObservationAuditReviewCatalogRegistry(repository, config)
        source = (bundle_id, verification.verification_id)
        with pytest.raises(ValueError, match="must be unique"):
            registry.create(
                catalog_name="duplicate",
                cataloged_at=AS_OF + timedelta(hours=11),
                sources=(source, source),
                source_revision="sha256:duplicate",
            )
        with pytest.raises(ValueError, match="cannot predate"):
            registry.create(
                catalog_name="early",
                cataloged_at=AS_OF + timedelta(hours=9),
                sources=(source,),
                source_revision="sha256:early",
            )
        manifest = ObservationAuditReviewExportRegistry(
            repository, bundle_config
        ).manifest(bundle_id)
        artifact = tmp_path / manifest.artifact_path
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="artifact hash mismatch"):
            registry.create(
                catalog_name="tampered",
                cataloged_at=AS_OF + timedelta(hours=11),
                sources=(source,),
                source_revision="sha256:tampered",
            )


def test_root_and_packaged_phase6g_migrations_match() -> None:
    root = ROOT / "migrations" / "034_phase_6g_observation_audit_review_catalogs.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "034_phase_6g_observation_audit_review_catalogs.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
