from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6g import seed_verified_bundle
from trading_system.operations import (
    ProspectiveReviewPlanConfigError,
    ProspectiveReviewPlanRegistry,
    load_prospective_review_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6i.v1.yaml"


def create_plan(repository: SQLiteRepository) -> tuple[ProspectiveReviewPlanRegistry, str]:
    registry = ProspectiveReviewPlanRegistry(
        repository, load_prospective_review_plan_config(CONFIG)
    )
    plan = registry.create_plan(
        catalog_name="prospective-catalog",
        registered_at=AS_OF + timedelta(hours=9, minutes=30),
        slots=(("slot-b", AS_OF + timedelta(hours=12)), ("slot-a", AS_OF + timedelta(hours=11))),
        source_revision="sha256:prospective-plan",
    )
    assert registry.insert_plan(plan) is True
    return registry, plan.plan_id


def test_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_prospective_review_plan_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["consensus_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewPlanConfigError, match="no authority"):
        load_prospective_review_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["completion_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveReviewPlanConfigError, match="cannot invent"):
        load_prospective_review_plan_config(invalid)


def test_plan_requires_registration_before_unique_slots(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        registry = ProspectiveReviewPlanRegistry(
            repository, load_prospective_review_plan_config(CONFIG)
        )
        with pytest.raises(ValueError, match="precede"):
            registry.create_plan(
                catalog_name="late",
                registered_at=AS_OF + timedelta(hours=11),
                slots=(("slot-a", AS_OF + timedelta(hours=11)),),
                source_revision="sha256:late",
            )
        with pytest.raises(ValueError, match="unique"):
            registry.create_plan(
                catalog_name="duplicate",
                registered_at=AS_OF,
                slots=(
                    ("slot-a", AS_OF + timedelta(hours=11)),
                    ("slot-a", AS_OF + timedelta(hours=12)),
                ),
                source_revision="sha256:duplicate",
            )


def test_binding_is_verified_single_slot_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
        registry, plan_id = create_plan(repository)
        binding = registry.bind(
            plan_id=plan_id,
            slot_id="slot-a",
            bundle_id=bundle_id,
            verification_id=verification.verification_id,
            bound_at=AS_OF + timedelta(hours=10, minutes=30),
            source_revision="sha256:binding",
        )
        assert registry.insert_binding(binding) is True
        assert registry.insert_binding(binding) is False
        status = registry.status(plan_id)
        assert status["resolved_count"] == 1
        assert status["pending_slot_ids"] == ["slot-b"]
        assert status["complete"] is False
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status = ProspectiveReviewPlanRegistry(
            repository, load_prospective_review_plan_config(CONFIG)
        ).status(plan_id)
        assert status["resolved_count"] == 1


def test_corrupt_binding_and_duplicate_bundle_fail_closed(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
        registry, plan_id = create_plan(repository)
        first = registry.bind(
            plan_id=plan_id,
            slot_id="slot-a",
            bundle_id=bundle_id,
            verification_id=verification.verification_id,
            bound_at=AS_OF + timedelta(hours=10, minutes=30),
            source_revision="sha256:first",
        )
        assert registry.insert_binding(first) is True
        second = registry.bind(
            plan_id=plan_id,
            slot_id="slot-b",
            bundle_id=bundle_id,
            verification_id=verification.verification_id,
            bound_at=AS_OF + timedelta(hours=10, minutes=31),
            source_revision="sha256:second",
        )
        with pytest.raises(ValueError, match="already bound"):
            registry.insert_binding(second)
        repository.connection.execute(
            "UPDATE operations_prospective_review_bindings SET payload_hash=? WHERE binding_id=?",
            ("sha256:" + "0" * 64, first.binding_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            registry.status(plan_id)


def test_phase6i_migration_copies_match() -> None:
    root = ROOT / "migrations" / "036_phase_6i_prospective_review_slots.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
