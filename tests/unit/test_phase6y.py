from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import CONFIG as PROPOSAL_CONFIG
from tests.unit.test_phase6u import create_proposal, verified_review
from tests.unit.test_phase6u import registry as proposal_registry
from tests.unit.test_phase6v import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6x import CONFIG as PLAN_CONFIG
from tests.unit.test_phase6x import registry as plan_registry
from trading_system.operations import (
    ArtifactTrustProposalMaterializationConfigError,
    ArtifactTrustProposalMaterializationRegistry,
    load_artifact_trust_policy_proposal_config,
    load_artifact_trust_proposal_catalog_config,
    load_artifact_trust_proposal_materialization_config,
    load_artifact_trust_proposal_plan_config,
    load_artifact_trust_review_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6y.v1.yaml"


def registry(repository: SQLiteRepository) -> ArtifactTrustProposalMaterializationRegistry:
    return ArtifactTrustProposalMaterializationRegistry(
        repository,
        load_artifact_trust_proposal_materialization_config(CONFIG),
        load_artifact_trust_proposal_plan_config(PLAN_CONFIG),
        load_artifact_trust_policy_proposal_config(PROPOSAL_CONFIG),
        load_artifact_trust_review_export_config(REVIEW_CONFIG),
        load_artifact_trust_proposal_catalog_config(CATALOG_CONFIG),
    )


def complete_plan(repository: SQLiteRepository) -> str:
    export_id, verification_id = verified_review(repository)
    plans = plan_registry(repository)
    plan = plans.create_plan(
        plan_name="materialization-source",
        review_export_id=export_id,
        review_verification_id=verification_id,
        registered_at=AS_OF + timedelta(hours=26, minutes=30),
        slots=((
            "slot-a",
            AS_OF + timedelta(hours=27),
            AS_OF + timedelta(hours=28),
        ),),
        source_revision="sha256:phase6y-plan",
    )
    assert plans.insert_plan(plan)
    proposal = create_proposal(
        proposal_registry(repository),
        export_id,
        verification_id,
        proposed_at=AS_OF + timedelta(hours=27, minutes=15),
    )
    assert proposal_registry(repository).insert(proposal)
    binding = plans.bind(
        plan_id=plan.plan_id,
        slot_id="slot-a",
        proposal_id=proposal.proposal_id,
        bound_at=AS_OF + timedelta(hours=27, minutes=30),
        source_revision="sha256:phase6y-binding",
    )
    assert plans.insert_binding(binding)
    return plan.plan_id


def test_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_artifact_trust_proposal_materialization_config(
        CONFIG
    ).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["caller_membership_override_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalMaterializationConfigError, match="no authority"):
        load_artifact_trust_proposal_materialization_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["completion_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalMaterializationConfigError, match="cannot invent"):
        load_artifact_trust_proposal_materialization_config(invalid)


def test_materialization_is_deterministic_restart_safe_and_bounded(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id = complete_plan(repository)
        store = registry(repository)
        item = store.materialize(
            source_plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=28),
            cataloged_at=AS_OF + timedelta(hours=29),
            source_revision="sha256:phase6y-materialization",
        )
        assert item.complete_population_claim is False
        assert item.slot_count == 1
        assert store.insert(item)
        assert not store.insert(item)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        value = registry(repository).status(item.materialization_id)
    assert value["materialization_id"] == item.materialization_id
    assert value["complete_population_claim"] is False


def test_materialization_requires_complete_plan_and_causal_time(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        plans = plan_registry(repository)
        plan = plans.create_plan(
            plan_name="incomplete",
            review_export_id=export_id,
            review_verification_id=verification_id,
            registered_at=AS_OF + timedelta(hours=26, minutes=30),
            slots=((
                "slot-a",
                AS_OF + timedelta(hours=27),
                AS_OF + timedelta(hours=28),
            ),),
            source_revision="sha256:phase6y-incomplete",
        )
        assert plans.insert_plan(plan)
        store = registry(repository)
        with pytest.raises(ValueError, match="incomplete"):
            store.materialize(
                source_plan_id=plan.plan_id,
                materialized_at=AS_OF + timedelta(hours=28),
                cataloged_at=AS_OF + timedelta(hours=29),
                source_revision="sha256:phase6y-materialization",
            )
    with SQLiteRepository(tmp_path / "causal.sqlite") as repository:
        repository.migrate()
        plan_id = complete_plan(repository)
        store = registry(repository)
        with pytest.raises(ValueError, match="follow"):
            store.materialize(
                source_plan_id=plan_id,
                materialized_at=AS_OF + timedelta(hours=29),
                cataloged_at=AS_OF + timedelta(hours=29),
                source_revision="sha256:phase6y-materialization",
            )


def test_materialization_detects_stored_or_source_tampering(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plan_id = complete_plan(repository)
        store = registry(repository)
        item = store.materialize(
            source_plan_id=plan_id,
            materialized_at=AS_OF + timedelta(hours=28),
            cataloged_at=AS_OF + timedelta(hours=29),
            source_revision="sha256:phase6y-materialization",
        )
        assert store.insert(item)
        repository.connection.execute(
            """UPDATE operations_artifact_trust_proposal_materializations
            SET payload_hash='sha256:corrupt' WHERE materialization_id=?""",
            (item.materialization_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            store.status(item.materialization_id)


def test_phase6y_migration_copies_match() -> None:
    root = ROOT / "migrations" / "052_phase_6y_artifact_trust_proposal_materializations.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
