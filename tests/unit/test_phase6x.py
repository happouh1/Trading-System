from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import create_proposal, verified_review
from tests.unit.test_phase6u import registry as proposal_registry
from trading_system.operations import (
    ArtifactTrustProposalPlanConfigError,
    ArtifactTrustProposalPlanRegistry,
    ArtifactTrustReviewExportRegistry,
    load_artifact_trust_proposal_plan_config,
    load_artifact_trust_review_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6x.v1.yaml"


def registry(repository: SQLiteRepository) -> ArtifactTrustProposalPlanRegistry:
    reviews = ArtifactTrustReviewExportRegistry(
        repository, load_artifact_trust_review_export_config(REVIEW_CONFIG)
    )
    proposals = proposal_registry(repository)
    return ArtifactTrustProposalPlanRegistry(
        repository, load_artifact_trust_proposal_plan_config(CONFIG), proposals, reviews
    )


def test_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_artifact_trust_proposal_plan_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["proposal_content_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalPlanConfigError, match="no authority"):
        load_artifact_trust_proposal_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_slot_count_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalPlanConfigError, match="cannot invent"):
        load_artifact_trust_proposal_plan_config(invalid)


def test_plan_precedes_content_and_binding_is_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        store = registry(repository)
        plan = store.create_plan(
            plan_name="prospective-policy-proposals",
            review_export_id=export_id,
            review_verification_id=verification_id,
            registered_at=AS_OF + timedelta(hours=26, minutes=30),
            slots=(("slot-a", AS_OF + timedelta(hours=27),
                    AS_OF + timedelta(hours=27, minutes=30)),),
            source_revision="sha256:phase6x-plan",
        )
        assert store.insert_plan(plan)
        proposal = create_proposal(
            proposal_registry(repository), export_id, verification_id,
            proposed_at=AS_OF + timedelta(hours=27, minutes=15),
        )
        assert proposal_registry(repository).insert(proposal)
        binding = store.bind(
            plan_id=plan.plan_id, slot_id="slot-a", proposal_id=proposal.proposal_id,
            bound_at=AS_OF + timedelta(hours=27, minutes=20),
            source_revision="sha256:phase6x-binding",
        )
        assert store.insert_binding(binding)
        assert not store.insert_binding(binding)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        status = registry(repository).status(plan.plan_id)
    assert status["complete"] is True
    assert status["complete_population_claim"] is False
    assert status["resolved_count"] == 1


def test_plan_and_binding_reject_noncausal_or_wrong_evidence(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        store = registry(repository)
        with pytest.raises(ValueError, match="precede"):
            store.create_plan(
                plan_name="late", review_export_id=export_id,
                review_verification_id=verification_id,
                registered_at=AS_OF + timedelta(hours=27),
                slots=(("slot", AS_OF + timedelta(hours=27),
                        AS_OF + timedelta(hours=28)),),
                source_revision="sha256:late",
            )
        plan = store.create_plan(
            plan_name="window", review_export_id=export_id,
            review_verification_id=verification_id,
            registered_at=AS_OF + timedelta(hours=26, minutes=30),
            slots=(("slot", AS_OF + timedelta(hours=28), AS_OF + timedelta(hours=29)),),
            source_revision="sha256:plan",
        )
        assert store.insert_plan(plan)
        proposal = create_proposal(proposal_registry(repository), export_id, verification_id)
        assert proposal_registry(repository).insert(proposal)
        with pytest.raises(ValueError, match="within"):
            store.bind(
                plan_id=plan.plan_id, slot_id="slot", proposal_id=proposal.proposal_id,
                bound_at=AS_OF + timedelta(hours=28), source_revision="sha256:binding",
            )


def test_plan_rejects_proposal_content_already_inside_slot(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        proposal = create_proposal(proposal_registry(repository), export_id, verification_id)
        assert proposal_registry(repository).insert(proposal)
        store = registry(repository)
        plan = store.create_plan(
            plan_name="not-prospective",
            review_export_id=export_id,
            review_verification_id=verification_id,
            registered_at=AS_OF + timedelta(hours=26, minutes=30),
            slots=(("slot", AS_OF + timedelta(hours=27), AS_OF + timedelta(hours=28)),),
            source_revision="sha256:not-prospective",
        )
        with pytest.raises(ValueError, match="already exists"):
            store.insert_plan(plan)


def test_slot_and_proposal_can_only_bind_once(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        store = registry(repository)
        plan = store.create_plan(
            plan_name="unique", review_export_id=export_id,
            review_verification_id=verification_id,
            registered_at=AS_OF + timedelta(hours=26, minutes=30),
            slots=(("a", AS_OF + timedelta(hours=27), AS_OF + timedelta(hours=28)),
                   ("b", AS_OF + timedelta(hours=27),
                    AS_OF + timedelta(hours=28, minutes=30))),
            source_revision="sha256:plan",
        )
        assert store.insert_plan(plan)
        proposal = create_proposal(proposal_registry(repository), export_id, verification_id)
        assert proposal_registry(repository).insert(proposal)
        first = store.bind(plan_id=plan.plan_id, slot_id="a", proposal_id=proposal.proposal_id,
                           bound_at=AS_OF + timedelta(hours=28),
                           source_revision="sha256:first")
        assert store.insert_binding(first)
        with pytest.raises(ValueError, match="already bound"):
            store.insert_binding(first.__class__.create(
                plan_id=plan.plan_id, slot_id="b", proposal_id=proposal.proposal_id,
                bound_at=AS_OF + timedelta(hours=28), proposed_at=proposal.proposed_at,
                proposal_payload_hash=first.proposal_payload_hash,
                source_revision="sha256:second",
                config=load_artifact_trust_proposal_plan_config(CONFIG),
            ))


def test_bound_proposal_tampering_is_detected(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        store = registry(repository)
        plan = store.create_plan(
            plan_name="tamper", review_export_id=export_id,
            review_verification_id=verification_id,
            registered_at=AS_OF + timedelta(hours=26, minutes=30),
            slots=(("slot", AS_OF + timedelta(hours=27), AS_OF + timedelta(hours=28)),),
            source_revision="sha256:plan",
        )
        assert store.insert_plan(plan)
        proposal = create_proposal(proposal_registry(repository), export_id, verification_id)
        assert proposal_registry(repository).insert(proposal)
        binding = store.bind(plan_id=plan.plan_id, slot_id="slot",
                             proposal_id=proposal.proposal_id,
                             bound_at=AS_OF + timedelta(hours=28),
                             source_revision="sha256:binding")
        assert store.insert_binding(binding)
        repository.connection.execute(
            """UPDATE operations_artifact_trust_policy_proposals
            SET payload_hash=? WHERE proposal_id=?""",
            ("sha256:corrupt", proposal.proposal_id),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            store.status(plan.plan_id)


def test_phase6x_migration_copies_match() -> None:
    root = ROOT / "migrations" / "051_phase_6x_prospective_artifact_trust_proposal_slots.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
