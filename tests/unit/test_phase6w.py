from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6v import catalog_registry, proposals
from trading_system.operations import (
    ArtifactTrustProposalCatalogPlanConfigError,
    ArtifactTrustProposalCatalogPlanRegistry,
    ArtifactTrustProposalCatalogReconciliationStatus,
    load_artifact_trust_proposal_catalog_plan_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6w.v1.yaml"


def plan_registry(repository: SQLiteRepository) -> ArtifactTrustProposalCatalogPlanRegistry:
    catalogs = catalog_registry(repository)
    return ArtifactTrustProposalCatalogPlanRegistry(
        repository,
        load_artifact_trust_proposal_catalog_plan_config(CONFIG),
        catalogs.proposals,
        catalogs,
    )


def seed_plan_and_catalog(repository: SQLiteRepository) -> tuple[str, str]:
    proposal_ids = proposals(repository)
    store = plan_registry(repository)
    plan = store.create_plan(
        proposal_ids=proposal_ids,
        registered_at=AS_OF + timedelta(hours=29),
        source_revision="sha256:phase6w-plan",
    )
    assert store.insert_plan(plan)
    catalog = catalog_registry(repository).create(
        proposal_ids=proposal_ids,
        cataloged_at=AS_OF + timedelta(hours=30),
        source_revision="sha256:phase6w-catalog",
    )
    assert catalog_registry(repository).insert(catalog)
    return plan.plan_id, catalog.catalog_id


def test_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_artifact_trust_proposal_catalog_plan_config(CONFIG).config_hash.startswith(
        "sha256:"
    )
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["proposal_selection_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalCatalogPlanConfigError, match="no authority"):
        load_artifact_trust_proposal_catalog_plan_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_lead_time_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalCatalogPlanConfigError, match="cannot invent"):
        load_artifact_trust_proposal_catalog_plan_config(invalid)


def test_plan_and_matched_reconciliation_are_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
        store = plan_registry(repository)
        result = store.reconcile(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=AS_OF + timedelta(hours=31),
            source_revision="sha256:phase6w-match",
        )
        assert result.status is ArtifactTrustProposalCatalogReconciliationStatus.MATCHED
        assert store.insert_reconciliation(result)
        assert not store.insert_reconciliation(result)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        store = plan_registry(repository)
        assert store.plan(plan_id).plan_id == plan_id
        assert store.reconciliation(result.reconciliation_id)["status"] == "MATCHED"


def test_reconciliation_reports_membership_deviation_and_missing(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
        store = plan_registry(repository)
        plan = store.create_plan(
            proposal_ids=proposal_ids,
            registered_at=AS_OF + timedelta(hours=29),
            source_revision="sha256:phase6w-plan",
        )
        assert store.insert_plan(plan)
        catalog = catalog_registry(repository).create(
            proposal_ids=(proposal_ids[0],),
            cataloged_at=AS_OF + timedelta(hours=30),
            source_revision="sha256:phase6w-short-catalog",
        )
        assert catalog_registry(repository).insert(catalog)
        changed = store.reconcile(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            reconciled_at=AS_OF + timedelta(hours=31),
            source_revision="sha256:phase6w-deviation",
        )
        missing = store.reconcile(
            plan_id=plan.plan_id,
            catalog_id="missing-catalog",
            reconciled_at=AS_OF + timedelta(hours=31),
            source_revision="sha256:phase6w-missing",
        )
    assert changed.status is ArtifactTrustProposalCatalogReconciliationStatus.DEVIATION
    assert changed.reasons == (
        "PLANNED_PROPOSAL_MISSING",
        "PROPOSAL_PAYLOAD_ROOT_CHANGED",
    )
    assert missing.status is ArtifactTrustProposalCatalogReconciliationStatus.MISSING
    assert missing.reasons == ("CATALOG_MISSING",)


def test_plan_rejects_noncanonical_and_noncausal_sources(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
        store = plan_registry(repository)
        with pytest.raises(ValueError, match="sorted, and unique"):
            store.create_plan(
                proposal_ids=tuple(reversed(proposal_ids)),
                registered_at=AS_OF + timedelta(hours=29),
                source_revision="sha256:phase6w-plan",
            )
        with pytest.raises(ValueError, match="predate"):
            store.create_plan(
                proposal_ids=proposal_ids,
                registered_at=AS_OF + timedelta(hours=27),
                source_revision="sha256:phase6w-plan",
            )


def test_reconciliation_classifies_corrupt_catalog(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
        repository.connection.execute(
            """UPDATE operations_artifact_trust_proposal_catalogs
            SET payload_hash='sha256:corrupt' WHERE catalog_id=?""",
            (catalog_id,),
        )
        repository.connection.commit()
        result = plan_registry(repository).reconcile(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=AS_OF + timedelta(hours=31),
            source_revision="sha256:phase6w-corrupt",
        )
    assert result.status is ArtifactTrustProposalCatalogReconciliationStatus.CORRUPT
    assert result.reasons == ("CATALOG_PAYLOAD_CORRUPT",)


def test_plan_revalidates_proposal_payloads(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
        store = plan_registry(repository)
        plan = store.create_plan(
            proposal_ids=proposal_ids,
            registered_at=AS_OF + timedelta(hours=29),
            source_revision="sha256:phase6w-plan",
        )
        assert store.insert_plan(plan)
        repository.connection.execute(
            """UPDATE operations_artifact_trust_policy_proposals
            SET payload_hash='sha256:corrupt' WHERE proposal_id=?""",
            (proposal_ids[0],),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            store.plan(plan.plan_id)


def test_phase6w_migration_copies_match() -> None:
    root = ROOT / "migrations" / "050_phase_6w_artifact_trust_proposal_catalog_plans.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
