from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_prospective_controls import CONTROLS, PORTFOLIO, inputs
from tests.unit.test_prospective_credential_governance import governed_inputs
from tests.unit.test_prospective_entry import CAL, bar
from tests.unit.test_prospective_evidence import records
from tests.unit.test_prospective_evidence_review import review_inputs

from trading_system.execution_sim.prospective_control_registry import ProspectiveControlRegistry
from trading_system.execution_sim.prospective_controls import load_prospective_controls_config
from trading_system.execution_sim.prospective_credential_governance_registry import (
    ProspectiveCredentialGovernanceRegistry,
)
from trading_system.execution_sim.prospective_evidence_registry import ProspectiveEvidenceRegistry
from trading_system.execution_sim.prospective_evidence_review import evaluate_evidence_review
from trading_system.execution_sim.prospective_evidence_review_registry import (
    ProspectiveEvidenceReviewRegistry,
)
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import load_portfolio_config


def test_governed_review_is_restart_safe_and_gates_control(tmp_path: Path) -> None:
    entry, entry_assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    governance, credentials, attestations, issuances, timestamps, now = governed_inputs()
    request, _ = review_inputs()
    review_time = now + timedelta(minutes=2)
    review = evaluate_evidence_review(
        request, credentials=credentials, attestations=attestations,
        evaluated_at=review_time,
    )
    database = tmp_path / "governance.sqlite"
    with SQLiteRepository(database) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            entry, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        evidence = ProspectiveEvidenceRegistry(repo).corroborate(
            entry=entry, entry_assessment=entry_assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
            planned_hold_sessions=10, as_of=now,
        )
        reviews = ProspectiveEvidenceReviewRegistry(repo)
        assert reviews.register_request(request, evidence)
        for credential in credentials:
            assert reviews.record_credential(credential)
        for attestation in attestations:
            assert reviews.record_attestation(attestation)
        assert reviews.record_assessment(review)
        registry = ProspectiveCredentialGovernanceRegistry(repo)
        for issuance in issuances:
            assert registry.record_issuance(issuance)
        for timestamp in timestamps:
            assert registry.record_timestamp(timestamp)
        assert registry.record_assessment(governance, review)
        control = ProspectiveControlRegistry(repo).assess_governed_evidence_bound(
            entry=entry, entry_assessment=entry_assessment, evidence=evidence, review=review,
            governance=governance, portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=governance.evaluated_at,
        )
        assert control.status == "CONTROL_APPROVED"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_governed_review_assessments")
    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        ProspectiveCredentialGovernanceRegistry(restarted).require_verified(
            governance, review, as_of=governance.evaluated_at,
        )
    assert review_time < governance.evaluated_at


def test_phase11l_migration_copies_match() -> None:
    root = Path(__file__).parents[2]
    assert (root / "migrations/101_prospective_credential_governance.sql").read_bytes() == (
        root / "src/trading_system/persistence/migrations/101_prospective_credential_governance.sql"
    ).read_bytes()
