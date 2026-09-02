from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6g import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6g import seed_verified_bundle
from trading_system.operations import (
    ObservationAuditReviewCatalogRegistry,
    ReviewCatalogPlanConfigError,
    ReviewCatalogPlanRegistry,
    ReviewCatalogReconciliationStatus,
    load_observation_audit_review_catalog_config,
    load_review_catalog_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6h.v1.yaml"


def seed_plan_and_catalog(repository: SQLiteRepository) -> tuple[str, str]:
    bundle_id, verification = seed_verified_bundle(repository)
    plan_config = load_review_catalog_plan_config(CONFIG)
    plan_registry = ReviewCatalogPlanRegistry(repository, plan_config)
    plan = plan_registry.create_plan(
        catalog_name="planned-catalog",
        registered_at=AS_OF + timedelta(hours=10, minutes=30),
        sources=((bundle_id, verification.verification_id),),
        source_revision="sha256:phase6h-plan",
    )
    assert plan_registry.insert_plan(plan) is True
    catalog_registry = ObservationAuditReviewCatalogRegistry(
        repository, load_observation_audit_review_catalog_config(CATALOG_CONFIG)
    )
    catalog = catalog_registry.create(
        catalog_name="planned-catalog",
        cataloged_at=AS_OF + timedelta(hours=11),
        sources=((bundle_id, verification.verification_id),),
        source_revision="sha256:phase6h-catalog",
    )
    assert catalog_registry.insert(catalog) is True
    return plan.plan_id, catalog.catalog_id


def test_phase6h_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    config = load_review_catalog_plan_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["selection_unbiased_claim_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewCatalogPlanConfigError, match="no authority"):
        load_review_catalog_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_lead_time_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewCatalogPlanConfigError, match="cannot invent"):
        load_review_catalog_plan_config(invalid)


def test_plan_and_matched_reconciliation_are_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config = load_review_catalog_plan_config(CONFIG)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
        registry = ReviewCatalogPlanRegistry(repository, config)
        result = registry.reconcile(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:matched",
        )
        assert result.status is ReviewCatalogReconciliationStatus.MATCHED
        assert result.reasons == ()
        assert registry.insert_reconciliation(result) is True
        assert registry.insert_reconciliation(result) is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = ReviewCatalogPlanRegistry(repository, config)
        assert registry.plan(plan_id).plan_id == plan_id
        assert registry.reconciliation(result.reconciliation_id)["status"] == "MATCHED"


def test_reconciliation_records_changed_verification_and_missing_catalog(tmp_path: Path) -> None:
    config = load_review_catalog_plan_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
        plan_registry = ReviewCatalogPlanRegistry(repository, config)
        plan = plan_registry.create_plan(
            catalog_name="planned-catalog",
            registered_at=AS_OF + timedelta(hours=10, minutes=30),
            sources=((bundle_id, "different-verification"),),
            source_revision="sha256:changed-plan",
        )
        assert plan_registry.insert_plan(plan) is True
        catalog_registry = ObservationAuditReviewCatalogRegistry(
            repository, load_observation_audit_review_catalog_config(CATALOG_CONFIG)
        )
        catalog = catalog_registry.create(
            catalog_name="planned-catalog",
            cataloged_at=AS_OF + timedelta(hours=11),
            sources=((bundle_id, verification.verification_id),),
            source_revision="sha256:actual-catalog",
        )
        assert catalog_registry.insert(catalog) is True
        changed = plan_registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            reconciled_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:changed",
        )
        assert changed.status is ReviewCatalogReconciliationStatus.DEVIATION
        assert changed.reasons == ("BUNDLE_VERIFICATION_CHANGED",)
        missing = plan_registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id="missing-catalog-id",
            reconciled_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:missing",
        )
        assert missing.status is ReviewCatalogReconciliationStatus.MISSING
        assert missing.reasons == ("CATALOG_MISSING",)


def test_reconciliation_marks_catalog_created_before_plan_corrupt(tmp_path: Path) -> None:
    config = load_review_catalog_plan_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
        catalog_registry = ObservationAuditReviewCatalogRegistry(
            repository, load_observation_audit_review_catalog_config(CATALOG_CONFIG)
        )
        catalog = catalog_registry.create(
            catalog_name="late-plan",
            cataloged_at=AS_OF + timedelta(hours=11),
            sources=((bundle_id, verification.verification_id),),
            source_revision="sha256:early-catalog",
        )
        assert catalog_registry.insert(catalog) is True
        registry = ReviewCatalogPlanRegistry(repository, config)
        plan = registry.create_plan(
            catalog_name="late-plan",
            registered_at=AS_OF + timedelta(hours=11, minutes=30),
            sources=((bundle_id, verification.verification_id),),
            source_revision="sha256:late-plan",
        )
        assert registry.insert_plan(plan) is True
        result = registry.reconcile(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            reconciled_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:corrupt",
        )
    assert result.status is ReviewCatalogReconciliationStatus.CORRUPT
    assert result.reasons == ("CATALOG_NOT_AFTER_PLAN",)


def test_reconciliation_detects_corrupt_catalog_child_evidence(tmp_path: Path) -> None:
    config = load_review_catalog_plan_config(CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
        repository.connection.execute(
            """UPDATE operations_observation_audit_review_catalog_entries
               SET payload_hash = ? WHERE catalog_id = ?""",
            ("sha256:" + "0" * 64, catalog_id),
        )
        repository.connection.commit()
        result = ReviewCatalogPlanRegistry(repository, config).reconcile(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=AS_OF + timedelta(hours=12),
            source_revision="sha256:corrupt-child",
        )
    assert result.status is ReviewCatalogReconciliationStatus.CORRUPT
    assert result.reasons == ("CATALOG_PAYLOAD_CORRUPT",)


def test_root_and_packaged_phase6h_migrations_match() -> None:
    root = ROOT / "migrations" / "035_phase_6h_review_catalog_plans.sql"
    packaged = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "035_phase_6h_review_catalog_plans.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
