from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6g import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6g import seed_verified_bundle
from tests.unit.test_phase6i import CONFIG as PLAN_CONFIG
from trading_system.operations import (
    ProspectiveCatalogMaterializationConfigError,
    ProspectiveCatalogMaterializationRegistry,
    ProspectiveReviewPlanRegistry,
    load_observation_audit_review_catalog_config,
    load_prospective_catalog_materialization_config,
    load_prospective_review_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6j.v1.yaml"


def seed_complete_plan(repository: SQLiteRepository) -> str:
    bundle_id, verification = seed_verified_bundle(repository)
    plans = ProspectiveReviewPlanRegistry(
        repository, load_prospective_review_plan_config(PLAN_CONFIG)
    )
    plan = plans.create_plan(
        catalog_name="materialized-catalog",
        registered_at=AS_OF + timedelta(hours=9, minutes=30),
        slots=(("review-window-1", AS_OF + timedelta(hours=11)),),
        source_revision="sha256:phase6j-plan",
    )
    assert plans.insert_plan(plan) is True
    binding = plans.bind(
        plan_id=plan.plan_id,
        slot_id="review-window-1",
        bundle_id=bundle_id,
        verification_id=verification.verification_id,
        bound_at=AS_OF + timedelta(hours=10, minutes=30),
        source_revision="sha256:phase6j-binding",
    )
    assert plans.insert_binding(binding) is True
    return plan.plan_id


def registry(repository: SQLiteRepository) -> ProspectiveCatalogMaterializationRegistry:
    return ProspectiveCatalogMaterializationRegistry(
        repository,
        load_prospective_catalog_materialization_config(CONFIG),
        load_prospective_review_plan_config(PLAN_CONFIG),
        load_observation_audit_review_catalog_config(CATALOG_CONFIG),
    )


def test_phase6j_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_prospective_catalog_materialization_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["caller_membership_override_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveCatalogMaterializationConfigError, match="no authority"):
        load_prospective_catalog_materialization_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["review_quality_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveCatalogMaterializationConfigError, match="cannot invent"):
        load_prospective_catalog_materialization_config(invalid)


def test_materialization_requires_complete_plan(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plans = ProspectiveReviewPlanRegistry(
            repository, load_prospective_review_plan_config(PLAN_CONFIG)
        )
        plan = plans.create_plan(
            catalog_name="incomplete",
            registered_at=AS_OF,
            slots=(("pending", AS_OF + timedelta(hours=11)),),
            source_revision="sha256:incomplete",
        )
        plans.insert_plan(plan)
        with pytest.raises(ValueError, match="incomplete"):
            registry(repository).materialize(
                plan_id=plan.plan_id,
                materialized_at=AS_OF + timedelta(hours=12),
                source_revision="sha256:must-fail",
            )


def test_materialization_is_exact_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id = seed_complete_plan(repository)
        service = registry(repository)
        evidence = service.materialize(
            plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=11),
            source_revision="sha256:materialized",
        )
        assert service.insert(evidence) is True
        assert service.insert(evidence) is False
        assert service.status(evidence.materialization_id)["plan_id"] == plan_id
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert (
            registry(repository).status(evidence.materialization_id)["catalog_id"]
            == evidence.catalog_id
        )


def test_materialization_detects_tampered_provenance(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plan_id = seed_complete_plan(repository)
        service = registry(repository)
        evidence = service.materialize(
            plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=11),
            source_revision="sha256:tamper",
        )
        service.insert(evidence)
        repository.connection.execute(
            "UPDATE operations_prospective_catalog_materializations SET payload_hash=?",
            ("sha256:" + "0" * 64,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            service.status(evidence.materialization_id)


def test_phase6j_migration_copies_match() -> None:
    root = ROOT / "migrations" / "037_phase_6j_prospective_catalog_materializations.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
