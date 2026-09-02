from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6n import seed_verified_bundle
from trading_system.operations import (
    ProspectiveReviewBundlePlanConfigError,
    ProspectiveReviewBundlePlanRegistry,
    load_prospective_chain_review_catalog_config,
    load_prospective_review_bundle_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6p.v1.yaml"


def registry(repository: SQLiteRepository) -> ProspectiveReviewBundlePlanRegistry:
    return ProspectiveReviewBundlePlanRegistry(
        repository,
        load_prospective_review_bundle_plan_config(CONFIG),
        load_prospective_chain_review_catalog_config(CATALOG_CONFIG),
    )


def create_plan(repository: SQLiteRepository) -> tuple[ProspectiveReviewBundlePlanRegistry, str]:
    service = registry(repository)
    plan = service.create_plan(
        catalog_name="future-review-catalog",
        registered_at=AS_OF,
        slots=(
            ("slot-b", AS_OF + timedelta(hours=20)),
            ("slot-a", AS_OF + timedelta(hours=19)),
        ),
        source_revision="sha256:phase6p-plan",
    )
    assert service.insert_plan(plan)
    return service, plan.plan_id


def test_phase6p_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["consensus_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundlePlanConfigError, match="no authority"):
        load_prospective_review_bundle_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["timing_tolerance_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewBundlePlanConfigError, match="cannot invent"):
        load_prospective_review_bundle_plan_config(invalid)


def test_plan_requires_prior_registration_and_unique_slots(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        service = registry(repository)
        with pytest.raises(ValueError, match="precede"):
            service.create_plan(
                catalog_name="late",
                registered_at=AS_OF + timedelta(hours=19),
                slots=(("slot", AS_OF + timedelta(hours=19)),),
                source_revision="sha256:late",
            )
        with pytest.raises(ValueError, match="unique"):
            service.create_plan(
                catalog_name="duplicate",
                registered_at=AS_OF,
                slots=(
                    ("slot", AS_OF + timedelta(hours=19)),
                    ("slot", AS_OF + timedelta(hours=20)),
                ),
                source_revision="sha256:duplicate",
            )


def test_verified_binding_is_single_use_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
        service, plan_id = create_plan(repository)
        binding = service.bind(
            plan_id=plan_id,
            slot_id="slot-a",
            bundle_id=bundle_id,
            verification_id=verification_id,
            bound_at=AS_OF + timedelta(hours=18),
            source_revision="sha256:phase6p-binding",
        )
        assert service.insert_binding(binding)
        assert not service.insert_binding(binding)
        with pytest.raises(ValueError, match="already bound"):
            second = service.bind(
                plan_id=plan_id,
                slot_id="slot-b",
                bundle_id=bundle_id,
                verification_id=verification_id,
                bound_at=AS_OF + timedelta(hours=18),
                source_revision="sha256:phase6p-duplicate",
            )
            service.insert_binding(second)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status = registry(repository).status(plan_id)
    assert status["resolved_count"] == 1
    assert status["pending_slot_ids"] == ["slot-b"]


def test_phase6p_migration_copies_match() -> None:
    root = ROOT / "migrations" / "043_phase_6p_prospective_review_bundle_slots.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
