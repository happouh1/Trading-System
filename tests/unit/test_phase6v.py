from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6u import ANSWERS, create_proposal, registry, verified_review
from trading_system.operations import (
    ArtifactTrustProposalCatalogConfigError,
    ArtifactTrustProposalCatalogRegistry,
    ArtifactTrustProposalCatalogStatus,
    load_artifact_trust_proposal_catalog_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6v.v1.yaml"


def catalog_registry(repository: SQLiteRepository) -> ArtifactTrustProposalCatalogRegistry:
    return ArtifactTrustProposalCatalogRegistry(
        repository, load_artifact_trust_proposal_catalog_config(CONFIG), registry(repository)
    )


def proposals(repository: SQLiteRepository) -> tuple[str, str]:
    export_id, verification_id = verified_review(repository)
    store = registry(repository)
    first = create_proposal(store, export_id, verification_id)
    changed = dict(ANSWERS)
    changed["receiving_verifier"] = "alternative-verifier-reference"
    second = create_proposal(
        store,
        export_id,
        verification_id,
        proposed_at=AS_OF + timedelta(hours=28),
        answers=changed,
    )
    assert store.insert(first)
    assert store.insert(second)
    ordered = sorted((first.proposal_id, second.proposal_id))
    return ordered[0], ordered[1]


def test_config_rejects_authority_and_thresholds(tmp_path: Path) -> None:
    assert load_artifact_trust_proposal_catalog_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["proposal_selection_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalCatalogConfigError, match="no selection"):
        load_artifact_trust_proposal_catalog_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["quorum_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustProposalCatalogConfigError, match="cannot invent"):
        load_artifact_trust_proposal_catalog_config(invalid)


def test_catalog_is_descriptive_deterministic_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
        store = catalog_registry(repository)
        item = store.create(
            proposal_ids=proposal_ids,
            cataloged_at=AS_OF + timedelta(hours=29),
            source_revision="sha256:phase6v-catalog",
        )
        assert item.status is ArtifactTrustProposalCatalogStatus.VALUES_DIFFER_UNAUTHENTICATED
        verifier = next(
            value for value in item.comparisons if value.field_name == "receiving_verifier"
        )
        assert not verifier.all_values_identical
        assert store.insert(item)
        assert not store.insert(item)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert catalog_registry(repository).catalog(item.catalog_id) == item


def test_catalog_rejects_noncanonical_and_noncausal_inputs(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
        store = catalog_registry(repository)
        with pytest.raises(ValueError, match="sorted, and unique"):
            store.create(
                proposal_ids=tuple(reversed(proposal_ids)),
                cataloged_at=AS_OF + timedelta(hours=29),
                source_revision="sha256:phase6v-catalog",
            )
        with pytest.raises(ValueError, match="predate"):
            store.create(
                proposal_ids=proposal_ids,
                cataloged_at=AS_OF + timedelta(hours=27),
                source_revision="sha256:phase6v-catalog",
            )


def test_catalog_revalidates_proposal_payloads(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
        repository.connection.execute(
            """UPDATE operations_artifact_trust_policy_proposals
            SET payload_hash='sha256:corrupt' WHERE proposal_id=?""",
            (proposal_ids[0],),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            catalog_registry(repository).create(
                proposal_ids=proposal_ids,
                cataloged_at=AS_OF + timedelta(hours=29),
                source_revision="sha256:phase6v-catalog",
            )


def test_phase6v_migration_copies_match() -> None:
    root = ROOT / "migrations" / "049_phase_6v_artifact_trust_proposal_catalogs.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
