from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6m import bundle_service, seed_review_history
from trading_system.operations import (
    ProspectiveChainReviewCatalogConfigError,
    ProspectiveChainReviewCatalogRegistry,
    load_prospective_chain_review_catalog_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6n.v1.yaml"


def seed_verified_bundle(repository: SQLiteRepository) -> tuple[str, str]:
    export_id, source_verification_id = seed_review_history(repository)
    service = bundle_service(repository)
    manifest = service.export(
        export_id=export_id,
        source_verification_id=source_verification_id,
        bundled_at=AS_OF + timedelta(hours=16),
        source_revision="sha256:phase6n-bundle",
    )
    verification = service.verify(
        bundle_id=manifest.bundle_id,
        verified_at=AS_OF + timedelta(hours=17),
        source_revision="sha256:phase6n-verification",
    )
    return manifest.bundle_id, verification.verification_id


def catalog_registry(repository: SQLiteRepository) -> ProspectiveChainReviewCatalogRegistry:
    config = load_prospective_chain_review_catalog_config(CONFIG)
    return ProspectiveChainReviewCatalogRegistry(repository, config)


def test_phase6n_config_rejects_authority_thresholds_and_paths(tmp_path: Path) -> None:
    assert (
        load_prospective_chain_review_catalog_config(CONFIG).source_directory
        == "prospective_chain_review_bundles"
    )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["consensus_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewCatalogConfigError, match="no authority"):
        load_prospective_chain_review_catalog_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_bundle_count_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewCatalogConfigError, match="cannot invent"):
        load_prospective_chain_review_catalog_config(invalid)


def test_catalog_is_canonical_idempotent_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
        registry = catalog_registry(repository)
        catalog = registry.create(
            catalog_name="prospective-review-wave-1",
            cataloged_at=AS_OF + timedelta(hours=18),
            sources=((bundle_id, verification_id),),
            source_revision="sha256:phase6n-catalog",
        )
        assert registry.insert(catalog)
        assert not registry.insert(catalog)
        assert catalog.bundle_count == 1
        assert catalog.total_review_count == 2
        assert catalog.total_active_review_count == 1
        assert catalog.total_summary_eligible_count == 1
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert catalog_registry(repository).status(catalog.catalog_id) == catalog


def test_catalog_rejects_duplicates_future_time_and_tampering(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
        registry = catalog_registry(repository)
        with pytest.raises(ValueError, match="unique"):
            registry.create(
                catalog_name="duplicates",
                cataloged_at=AS_OF + timedelta(hours=18),
                sources=((bundle_id, verification_id), (bundle_id, verification_id)),
                source_revision="sha256:duplicates",
            )
        with pytest.raises(ValueError, match="cannot predate"):
            registry.create(
                catalog_name="early",
                cataloged_at=AS_OF + timedelta(hours=16, minutes=30),
                sources=((bundle_id, verification_id),),
                source_revision="sha256:early",
            )
        path = repository.path.resolve().parent / repository.connection.execute(
            "SELECT artifact_path FROM operations_prospective_chain_review_bundles"
        ).fetchone()[0]
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="artifact hash mismatch"):
            registry.create(
                catalog_name="tampered",
                cataloged_at=AS_OF + timedelta(hours=18),
                sources=((bundle_id, verification_id),),
                source_revision="sha256:tampered",
            )


def test_catalog_normalizes_source_order(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        first_bundle, first_verification = seed_verified_bundle(repository)
        source = repository.connection.execute(
            """SELECT export_id,source_verification_id
               FROM operations_prospective_chain_review_bundles WHERE bundle_id=?""",
            (first_bundle,),
        ).fetchone()
        assert source is not None
        export_id, source_verification_id = str(source[0]), str(source[1])
        service = bundle_service(repository)
        second = service.export(
            export_id=export_id,
            source_verification_id=source_verification_id,
            bundled_at=AS_OF + timedelta(hours=18),
            source_revision="sha256:phase6n-second-bundle",
        )
        second_verification = service.verify(
            bundle_id=second.bundle_id,
            verified_at=AS_OF + timedelta(hours=19),
            source_revision="sha256:phase6n-second-verification",
        )
        registry = catalog_registry(repository)
        sources = (
            (second.bundle_id, second_verification.verification_id),
            (first_bundle, first_verification),
        )
        catalog = registry.create(
            catalog_name="canonical-order",
            cataloged_at=AS_OF + timedelta(hours=20),
            sources=sources,
            source_revision="sha256:canonical-order",
        )
        assert tuple(item.bundle_id for item in catalog.entries) == tuple(
            sorted((first_bundle, second.bundle_id))
        )


def test_phase6n_migration_copies_match() -> None:
    root = ROOT / "migrations" / "041_phase_6n_prospective_chain_review_catalogs.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
