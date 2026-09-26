from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tests.unit.test_prospective_controls import CONTROLS, PORTFOLIO, inputs
from tests.unit.test_prospective_entry import CAL, bar
from tests.unit.test_prospective_evidence import records
from tests.unit.test_prospective_evidence_review import CONFIG

from trading_system.execution_sim.prospective_control_registry import ProspectiveControlRegistry
from trading_system.execution_sim.prospective_controls import load_prospective_controls_config
from trading_system.execution_sim.prospective_evidence_registry import ProspectiveEvidenceRegistry
from trading_system.execution_sim.prospective_evidence_review import (
    build_evidence_review_attestation,
    build_evidence_review_credential,
    build_evidence_review_request,
    evaluate_evidence_review,
    evidence_review_message,
    load_evidence_review_config,
)
from trading_system.execution_sim.prospective_evidence_review_registry import (
    ProspectiveEvidenceReviewRegistry,
)
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import load_portfolio_config


def test_signed_review_is_restart_safe_and_gates_control(tmp_path: Path) -> None:
    request_entry, entry_assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    now = entry_assessment.known_at
    database = tmp_path / "review.sqlite"
    with SQLiteRepository(database) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request_entry, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        evidence = ProspectiveEvidenceRegistry(repo).corroborate(
            entry=request_entry, entry_assessment=entry_assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
            planned_hold_sessions=10, as_of=now,
        )
        review_request = build_evidence_review_request(
            load_evidence_review_config(CONFIG), evidence, requested_at=now,
            valid_from=now, valid_until=now + timedelta(hours=2),
            required_review_roles=("MARKET_REVIEWER", "PORTFOLIO_REVIEWER"),
        )
        review_registry = ProspectiveEvidenceReviewRegistry(repo)
        assert review_registry.register_request(review_request, evidence)
        credentials = []
        attestations = []
        for principal, role in (("alice", "MARKET_REVIEWER"), ("bob", "PORTFOLIO_REVIEWER")):
            private = Ed25519PrivateKey.generate()
            credential = build_evidence_review_credential(
                principal_id=principal, role=role,
                public_key=private.public_key().public_bytes_raw(),
                valid_from=now - timedelta(hours=1), valid_until=now + timedelta(days=1),
            )
            signed_at = now + timedelta(minutes=1)
            attestation = build_evidence_review_attestation(
                review_request, credential, signed_at=signed_at,
                signature=private.sign(
                    evidence_review_message(review_request, credential, signed_at)
                ),
            )
            assert review_registry.record_credential(credential)
            assert review_registry.record_attestation(attestation)
            credentials.append(credential)
            attestations.append(attestation)
        review = evaluate_evidence_review(
            review_request, credentials=tuple(credentials), attestations=tuple(attestations),
            evaluated_at=now + timedelta(minutes=2),
        )
        assert review_registry.record_assessment(review)
        control = ProspectiveControlRegistry(repo).assess_reviewed_evidence_bound(
            entry=request_entry, entry_assessment=entry_assessment, evidence=evidence,
            review=review, portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=review.evaluated_at,
        )
        assert control.status == "CONTROL_APPROVED"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_evidence_review_assessments")
    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        ProspectiveEvidenceReviewRegistry(restarted).require_verified(
            review, evidence, as_of=review.evaluated_at,
        )


def test_unstored_review_cannot_gate_control(tmp_path: Path) -> None:
    request_entry, entry_assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    now = entry_assessment.known_at
    with SQLiteRepository(tmp_path / "missing.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request_entry, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        evidence = ProspectiveEvidenceRegistry(repo).corroborate(
            entry=request_entry, entry_assessment=entry_assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
            planned_hold_sessions=10, as_of=now,
        )
        review_request = build_evidence_review_request(
            load_evidence_review_config(CONFIG), evidence, requested_at=now,
            valid_from=now, valid_until=now + timedelta(hours=2),
            required_review_roles=("RISK_REVIEWER",),
        )
        review = evaluate_evidence_review(
            review_request, credentials=(), attestations=(), evaluated_at=now,
        )
        with pytest.raises(ValueError, match="unavailable or changed"):
            ProspectiveControlRegistry(repo).assess_reviewed_evidence_bound(
                entry=request_entry, entry_assessment=entry_assessment, evidence=evidence,
                review=review, portfolio_config=load_portfolio_config(PORTFOLIO),
                controls_config=load_prospective_controls_config(CONTROLS), as_of=now,
            )


def test_phase11k_migration_copies_match() -> None:
    root = Path(__file__).parents[2]
    assert (root / "migrations/100_prospective_evidence_review.sql").read_bytes() == (
        root / "src/trading_system/persistence/migrations/100_prospective_evidence_review.sql"
    ).read_bytes()
