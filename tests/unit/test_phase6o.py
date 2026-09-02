from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6n import catalog_registry, seed_verified_bundle
from trading_system.operations import (
    ProspectiveChainReviewCatalogPlanConfigError,
    ProspectiveChainReviewCatalogPlanRegistry,
    ProspectiveChainReviewCatalogReconciliationStatus,
    load_prospective_chain_review_catalog_config,
    load_prospective_chain_review_catalog_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6o.v1.yaml"


def plan_registry(repository: SQLiteRepository) -> ProspectiveChainReviewCatalogPlanRegistry:
    return ProspectiveChainReviewCatalogPlanRegistry(
        repository,
        load_prospective_chain_review_catalog_plan_config(CONFIG),
        load_prospective_chain_review_catalog_config(CATALOG_CONFIG),
    )


def seed_plan_and_catalog(repository: SQLiteRepository) -> tuple[str, str]:
    bundle_id, verification_id = seed_verified_bundle(repository)
    registry = plan_registry(repository)
    plan = registry.create_plan(
        catalog_name="planned-prospective-review-catalog",
        registered_at=AS_OF + timedelta(hours=17, minutes=30),
        sources=((bundle_id, verification_id),),
        source_revision="sha256:phase6o-plan",
    )
    assert registry.insert_plan(plan)
    catalog = catalog_registry(repository).create(
        catalog_name="planned-prospective-review-catalog",
        cataloged_at=AS_OF + timedelta(hours=18),
        sources=((bundle_id, verification_id),),
        source_revision="sha256:phase6o-catalog",
    )
    assert catalog_registry(repository).insert(catalog)
    return plan.plan_id, catalog.catalog_id


def test_phase6o_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_prospective_chain_review_catalog_plan_config(CONFIG).config_hash.startswith(
        "sha256:"
    )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["selection_unbiased_claim_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewCatalogPlanConfigError, match="no authority"):
        load_prospective_chain_review_catalog_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_lead_time_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveChainReviewCatalogPlanConfigError, match="cannot invent"):
        load_prospective_chain_review_catalog_plan_config(invalid)


def test_plan_and_matched_reconciliation_are_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
        registry = plan_registry(repository)
        result = registry.reconcile(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=AS_OF + timedelta(hours=19),
            source_revision="sha256:phase6o-matched",
        )
        assert result.status is ProspectiveChainReviewCatalogReconciliationStatus.MATCHED
        assert registry.insert_reconciliation(result)
        assert not registry.insert_reconciliation(result)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = plan_registry(repository)
        assert registry.plan(plan_id).plan_id == plan_id
        assert registry.reconciliation(result.reconciliation_id)["status"] == "MATCHED"


def test_reconciliation_records_changed_verification_and_missing_catalog(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
        registry = plan_registry(repository)
        plan = registry.create_plan(
            catalog_name="planned",
            registered_at=AS_OF + timedelta(hours=17, minutes=30),
            sources=((bundle_id, "different-verification"),),
            source_revision="sha256:phase6o-different",
        )
        assert registry.insert_plan(plan)
        catalog = catalog_registry(repository).create(
            catalog_name="planned",
            cataloged_at=AS_OF + timedelta(hours=18),
            sources=((bundle_id, verification_id),),
            source_revision="sha256:phase6o-actual",
        )
        assert catalog_registry(repository).insert(catalog)
        changed = registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            reconciled_at=AS_OF + timedelta(hours=19),
            source_revision="sha256:phase6o-changed",
        )
        missing = registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id="missing-catalog",
            reconciled_at=AS_OF + timedelta(hours=19),
            source_revision="sha256:phase6o-missing",
        )
    assert changed.status is ProspectiveChainReviewCatalogReconciliationStatus.DEVIATION
    assert changed.reasons == ("BUNDLE_VERIFICATION_CHANGED",)
    assert missing.status is ProspectiveChainReviewCatalogReconciliationStatus.MISSING
    assert missing.reasons == ("CATALOG_MISSING",)


def test_reconciliation_marks_early_or_corrupt_catalog_explicitly(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
        catalog = catalog_registry(repository).create(
            catalog_name="late-plan",
            cataloged_at=AS_OF + timedelta(hours=18),
            sources=((bundle_id, verification_id),),
            source_revision="sha256:phase6o-early-catalog",
        )
        assert catalog_registry(repository).insert(catalog)
        registry = plan_registry(repository)
        plan = registry.create_plan(
            catalog_name="late-plan",
            registered_at=AS_OF + timedelta(hours=18, minutes=30),
            sources=((bundle_id, verification_id),),
            source_revision="sha256:phase6o-late-plan",
        )
        assert registry.insert_plan(plan)
        early = registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            reconciled_at=AS_OF + timedelta(hours=19),
            source_revision="sha256:phase6o-early",
        )
        repository.connection.execute(
            """UPDATE operations_prospective_chain_review_catalog_entries
               SET payload_hash=? WHERE catalog_id=?""",
            ("sha256:" + "0" * 64, catalog.catalog_id),
        )
        repository.connection.commit()
        corrupt = registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            reconciled_at=AS_OF + timedelta(hours=19),
            source_revision="sha256:phase6o-corrupt",
        )
    assert early.status is ProspectiveChainReviewCatalogReconciliationStatus.CORRUPT
    assert early.reasons == ("CATALOG_NOT_AFTER_PLAN",)
    assert corrupt.status is ProspectiveChainReviewCatalogReconciliationStatus.CORRUPT
    assert corrupt.reasons == ("CATALOG_PAYLOAD_CORRUPT",)


def test_phase6o_migration_copies_match() -> None:
    root = ROOT / "migrations" / "042_phase_6o_prospective_review_catalog_plans.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
