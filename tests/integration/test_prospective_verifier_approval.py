from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_prospective_controls import CONTROLS, PORTFOLIO, inputs
from tests.unit.test_prospective_credential_governance import CONFIG, governed_inputs
from tests.unit.test_prospective_entry import CAL, bar
from tests.unit.test_prospective_evidence import records
from tests.unit.test_prospective_evidence_review import review_inputs
from tests.unit.test_prospective_verifier_approval import signed_approval
from tests.unit.test_prospective_verifier_receipts import verifier_inputs

from trading_system.execution_sim.prospective_control_registry import ProspectiveControlRegistry
from trading_system.execution_sim.prospective_controls import load_prospective_controls_config
from trading_system.execution_sim.prospective_credential_governance import (
    load_credential_governance_config,
)
from trading_system.execution_sim.prospective_credential_governance_registry import (
    ProspectiveCredentialGovernanceRegistry,
)
from trading_system.execution_sim.prospective_evidence_registry import ProspectiveEvidenceRegistry
from trading_system.execution_sim.prospective_evidence_review import evaluate_evidence_review
from trading_system.execution_sim.prospective_evidence_review_registry import (
    ProspectiveEvidenceReviewRegistry,
)
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.execution_sim.prospective_verifier_approval import (
    evaluate_verifier_approval,
)
from trading_system.execution_sim.prospective_verifier_approval_registry import (
    ProspectiveVerifierApprovalRegistry,
)
from trading_system.execution_sim.prospective_verifier_receipt_registry import (
    ProspectiveVerifierReceiptRegistry,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    evaluate_receipt_bound_governance,
)
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import load_portfolio_config


def test_signed_bundle_approval_is_restart_safe_and_gates_control(tmp_path: Path) -> None:
    entry, entry_assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    _, credentials, attestations, issuances, timestamps, now = governed_inputs()
    review_request, _ = review_inputs()
    review = evaluate_evidence_review(
        review_request, credentials=credentials, attestations=attestations,
        evaluated_at=now + timedelta(minutes=2),
    )
    verification_receipts = verifier_inputs(
        credentials, attestations, issuances, timestamps, now,
    )
    governance, bound = evaluate_receipt_bound_governance(
        load_credential_governance_config(CONFIG), review, credentials=credentials,
        attestations=attestations, issuances=issuances, revocations=(),
        timestamps=timestamps, verification_receipts=verification_receipts,
        evaluated_at=now + timedelta(minutes=3),
    )
    approval_request, approval_credentials, approval_attestations = signed_approval(
        bound, now,
    )
    approval = evaluate_verifier_approval(
        approval_request, credentials=approval_credentials,
        attestations=approval_attestations, evaluated_at=now + timedelta(minutes=5),
    )
    database = tmp_path / "verifier-approval.sqlite"
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
        assert reviews.register_request(review_request, evidence)
        for credential in credentials:
            assert reviews.record_credential(credential)
        for attestation in attestations:
            assert reviews.record_attestation(attestation)
        assert reviews.record_assessment(review)
        governed = ProspectiveCredentialGovernanceRegistry(repo)
        for issuance in issuances:
            assert governed.record_issuance(issuance)
        for timestamp in timestamps:
            assert governed.record_timestamp(timestamp)
        assert governed.record_assessment(governance, review)
        receipts = ProspectiveVerifierReceiptRegistry(repo)
        for receipt in verification_receipts:
            assert receipts.record_receipt(receipt)
        assert receipts.record_assessment(bound, governance, verification_receipts)
        approvals = ProspectiveVerifierApprovalRegistry(repo)
        assert approvals.register_request(approval_request, bound)
        for approval_credential in approval_credentials:
            assert approvals.record_credential(approval_credential)
        for approval_attestation in approval_attestations:
            assert approvals.record_attestation(approval_attestation)
        assert approvals.record_assessment(approval)
        control = ProspectiveControlRegistry(repo).assess_approved_receipt_bound_evidence(
            entry=entry, entry_assessment=entry_assessment, evidence=evidence, review=review,
            governance=governance, receipt_bound=bound, approval=approval,
            portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=approval.evaluated_at,
        )
        assert control.status == "CONTROL_APPROVED"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_verifier_approval_assessments")
    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        ProspectiveVerifierApprovalRegistry(restarted).require_approved(
            approval, bound, as_of=approval.evaluated_at,
        )


def test_phase11n_migration_copies_match() -> None:
    root = Path(__file__).parents[2]
    assert (root / "migrations/103_prospective_verifier_approval.sql").read_bytes() == (
        root
        / "src/trading_system/persistence/migrations/103_prospective_verifier_approval.sql"
    ).read_bytes()
