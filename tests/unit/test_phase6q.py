from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6n import seed_verified_bundle
from tests.unit.test_phase6o import CONFIG as CATALOG_PLAN_CONFIG
from tests.unit.test_phase6p import CONFIG as PLAN_CONFIG
from trading_system.operations import (
    ProspectiveReviewBundleMaterializationConfigError,
    ProspectiveReviewBundleMaterializationRegistry,
    ProspectiveReviewBundlePlanRegistry,
    load_prospective_chain_review_catalog_config,
    load_prospective_chain_review_catalog_plan_config,
    load_prospective_review_bundle_materialization_config,
    load_prospective_review_bundle_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6q.v1.yaml"


def materialization_registry(
    repository: SQLiteRepository,
) -> ProspectiveReviewBundleMaterializationRegistry:
    return ProspectiveReviewBundleMaterializationRegistry(
        repository,
        load_prospective_review_bundle_materialization_config(CONFIG),
        load_prospective_review_bundle_plan_config(PLAN_CONFIG),
        load_prospective_chain_review_catalog_plan_config(CATALOG_PLAN_CONFIG),
        load_prospective_chain_review_catalog_config(CATALOG_CONFIG),
    )


def seed_complete_plan(repository: SQLiteRepository) -> str:
    bundle_id, verification_id = seed_verified_bundle(repository)
    plans = ProspectiveReviewBundlePlanRegistry(
        repository,
        load_prospective_review_bundle_plan_config(PLAN_CONFIG),
        load_prospective_chain_review_catalog_config(CATALOG_CONFIG),
    )
    plan = plans.create_plan(
        catalog_name="future-review-catalog",
        registered_at=AS_OF,
        slots=(("review-window-1", AS_OF + timedelta(hours=19)),),
        source_revision="sha256:phase6q-plan",
    )
    assert plans.insert_plan(plan)
    binding = plans.bind(
        plan_id=plan.plan_id,
        slot_id="review-window-1",
        bundle_id=bundle_id,
        verification_id=verification_id,
        bound_at=AS_OF + timedelta(hours=18),
        source_revision="sha256:phase6q-binding",
    )
    assert plans.insert_binding(binding)
    return plan.plan_id


def test_phase6q_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["consensus_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundleMaterializationConfigError, match="no authority"):
        load_prospective_review_bundle_materialization_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_slot_count_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundleMaterializationConfigError, match="cannot invent"):
        load_prospective_review_bundle_materialization_config(invalid)


def test_materialization_requires_complete_plan_and_strict_times(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plans = ProspectiveReviewBundlePlanRegistry(
            repository,
            load_prospective_review_bundle_plan_config(PLAN_CONFIG),
            load_prospective_chain_review_catalog_config(CATALOG_CONFIG),
        )
        plan = plans.create_plan(
            catalog_name="incomplete",
            registered_at=AS_OF,
            slots=(("pending", AS_OF + timedelta(hours=19)),),
            source_revision="sha256:incomplete",
        )
        assert plans.insert_plan(plan)
        service = materialization_registry(repository)
        with pytest.raises(ValueError, match="incomplete"):
            service.materialize(
                source_plan_id=plan.plan_id,
                materialized_at=AS_OF + timedelta(hours=19),
                cataloged_at=AS_OF + timedelta(hours=20),
                source_revision="sha256:incomplete",
            )
        complete = seed_complete_plan(repository)
        with pytest.raises(ValueError, match="must follow"):
            service.materialize(
                source_plan_id=complete,
                materialized_at=AS_OF + timedelta(hours=19),
                cataloged_at=AS_OF + timedelta(hours=19),
                source_revision="sha256:bad-time",
            )


def test_materialization_is_deterministic_idempotent_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id = seed_complete_plan(repository)
        service = materialization_registry(repository)
        item = service.materialize(
            source_plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=19),
            cataloged_at=AS_OF + timedelta(hours=20),
            source_revision="sha256:phase6q-materialization",
        )
        assert service.insert(item)
        repeated = service.materialize(
            source_plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=19),
            cataloged_at=AS_OF + timedelta(hours=20),
            source_revision="sha256:phase6q-materialization",
        )
        assert repeated == item
        assert not service.insert(repeated)
        with pytest.raises(ValueError, match="already materialized differently"):
            service.materialize(
                source_plan_id=plan_id,
                materialized_at=AS_OF + timedelta(hours=19, minutes=1),
                cataloged_at=AS_OF + timedelta(hours=20),
                source_revision="sha256:phase6q-materialization",
            )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status = materialization_registry(repository).status(item.materialization_id)
    assert status["source_plan_id"] == plan_id
    assert status["slot_count"] == 1
    assert status["binding_root_hash"].startswith("sha256:")


def test_materialization_detects_persisted_corruption(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plan_id = seed_complete_plan(repository)
        service = materialization_registry(repository)
        item = service.materialize(
            source_plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=19),
            cataloged_at=AS_OF + timedelta(hours=20),
            source_revision="sha256:phase6q-corrupt",
        )
        assert service.insert(item)
        repository.connection.execute(
            """UPDATE operations_prospective_review_bundle_materializations
            SET payload_hash='sha256:corrupt' WHERE materialization_id=?""",
            (item.materialization_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="payload is corrupt"):
            service.status(item.materialization_id)


def test_phase6q_migration_copies_match() -> None:
    root = ROOT / "migrations" / "044_phase_6q_review_bundle_materializations.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
