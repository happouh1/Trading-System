"""Append-only offline prospective control receipts."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.execution_sim.prospective_controls import (
    ProspectiveControlAssessment,
    ProspectiveControlsConfig,
    assess_prospective_controls,
)
from trading_system.execution_sim.prospective_credential_governance import (
    GovernedReviewAssessment,
)
from trading_system.execution_sim.prospective_credential_governance_registry import (
    ProspectiveCredentialGovernanceRegistry,
)
from trading_system.execution_sim.prospective_evidence import CorroboratedProspectiveInputs
from trading_system.execution_sim.prospective_evidence_registry import ProspectiveEvidenceRegistry
from trading_system.execution_sim.prospective_evidence_review import EvidenceReviewAssessment
from trading_system.execution_sim.prospective_evidence_review_registry import (
    ProspectiveEvidenceReviewRegistry,
)
from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAssessment,
)
from trading_system.execution_sim.prospective_verifier_approval_registry import (
    ProspectiveVerifierApprovalRegistry,
)
from trading_system.execution_sim.prospective_verifier_receipt_registry import (
    ProspectiveVerifierReceiptRegistry,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
)
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import PortfolioCandidate, PortfolioConfig, PortfolioState
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveControlRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def assess(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        portfolio_state: PortfolioState, candidate: PortfolioCandidate,
        portfolio_config: PortfolioConfig, controls_config: ProspectiveControlsConfig,
        as_of: datetime,
    ) -> ProspectiveControlAssessment:
        result = assess_prospective_controls(
            entry=entry, entry_assessment=entry_assessment,
            portfolio_state=portfolio_state, candidate=candidate,
            portfolio_config=portfolio_config, controls_config=controls_config,
        )
        if result.known_at > as_of:
            raise ValueError("prospective control receipt unavailable at cutoff")
        payload, digest = canonical_json(result), canonical_hash(result)
        connection = self.repository.connection
        connection.execute("SAVEPOINT prospective_control")
        try:
            prior = connection.execute(
                "SELECT known_at, payload_json, payload_hash "
                "FROM prospective_control_assessments WHERE decision_id = ?",
                (entry.decision_id,),
            ).fetchone()
            if prior is not None:
                if datetime.fromisoformat(prior[0]) > as_of:
                    raise ValueError("stored prospective control unavailable at cutoff")
                if canonical_hash(json.loads(prior[1])) != prior[2]:
                    raise ValueError("stored prospective control integrity failure")
                if prior != (result.known_at.isoformat(), payload, digest):
                    raise ValueError("prospective control assessment cannot be revised")
            else:
                connection.execute(
                    "INSERT INTO prospective_control_assessments VALUES (?, ?, ?, ?, ?)",
                    (entry.decision_id, result.known_at.isoformat(), result.status,
                     payload, digest),
                )
            connection.execute("RELEASE prospective_control")
            return result
        except Exception:
            connection.execute("ROLLBACK TO prospective_control")
            connection.execute("RELEASE prospective_control")
            raise

    def assess_evidence_bound(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        evidence: CorroboratedProspectiveInputs,
        portfolio_config: PortfolioConfig, controls_config: ProspectiveControlsConfig,
        as_of: datetime,
    ) -> ProspectiveControlAssessment:
        """Assess only after the exact corroborated evidence receipt is persisted."""
        if evidence.decision_id != entry.decision_id:
            raise ValueError("prospective evidence decision does not match entry")
        ProspectiveEvidenceRegistry(self.repository).require_stored(evidence, as_of=as_of)
        return self.assess(
            entry=entry, entry_assessment=entry_assessment,
            portfolio_state=evidence.portfolio_state, candidate=evidence.candidate,
            portfolio_config=portfolio_config, controls_config=controls_config,
            as_of=as_of,
        )

    def assess_reviewed_evidence_bound(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        evidence: CorroboratedProspectiveInputs, review: EvidenceReviewAssessment,
        portfolio_config: PortfolioConfig, controls_config: ProspectiveControlsConfig,
        as_of: datetime,
    ) -> ProspectiveControlAssessment:
        """Require stored, signed independent review before the evidence-bound control."""
        ProspectiveEvidenceReviewRegistry(self.repository).require_verified(
            review, evidence, as_of=as_of,
        )
        return self.assess_evidence_bound(
            entry=entry, entry_assessment=entry_assessment, evidence=evidence,
            portfolio_config=portfolio_config, controls_config=controls_config,
            as_of=as_of,
        )

    def assess_governed_evidence_bound(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        evidence: CorroboratedProspectiveInputs, review: EvidenceReviewAssessment,
        governance: GovernedReviewAssessment, portfolio_config: PortfolioConfig,
        controls_config: ProspectiveControlsConfig, as_of: datetime,
    ) -> ProspectiveControlAssessment:
        """Require exact stored Phase 11L governance before evaluating controls."""
        ProspectiveCredentialGovernanceRegistry(self.repository).require_verified(
            governance, review, as_of=as_of,
        )
        return self.assess_reviewed_evidence_bound(
            entry=entry, entry_assessment=entry_assessment, evidence=evidence, review=review,
            portfolio_config=portfolio_config, controls_config=controls_config, as_of=as_of,
        )

    def assess_receipt_bound_evidence(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        evidence: CorroboratedProspectiveInputs, review: EvidenceReviewAssessment,
        governance: GovernedReviewAssessment, receipt_bound: ReceiptBoundGovernanceAssessment,
        portfolio_config: PortfolioConfig, controls_config: ProspectiveControlsConfig,
        as_of: datetime,
    ) -> ProspectiveControlAssessment:
        """Require immutable Phase 11M verifier outcomes before evaluating controls."""
        ProspectiveVerifierReceiptRegistry(self.repository).require_verified(
            receipt_bound, governance, as_of=as_of,
        )
        return self.assess_governed_evidence_bound(
            entry=entry, entry_assessment=entry_assessment, evidence=evidence, review=review,
            governance=governance, portfolio_config=portfolio_config,
            controls_config=controls_config, as_of=as_of,
        )

    def assess_approved_receipt_bound_evidence(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        evidence: CorroboratedProspectiveInputs, review: EvidenceReviewAssessment,
        governance: GovernedReviewAssessment, receipt_bound: ReceiptBoundGovernanceAssessment,
        approval: VerifierApprovalAssessment, portfolio_config: PortfolioConfig,
        controls_config: ProspectiveControlsConfig, as_of: datetime,
    ) -> ProspectiveControlAssessment:
        """Require an exact approved Phase 11N bundle before evaluating controls."""
        ProspectiveVerifierApprovalRegistry(self.repository).require_approved(
            approval, receipt_bound, as_of=as_of,
        )
        return self.assess_receipt_bound_evidence(
            entry=entry, entry_assessment=entry_assessment, evidence=evidence, review=review,
            governance=governance, receipt_bound=receipt_bound,
            portfolio_config=portfolio_config, controls_config=controls_config, as_of=as_of,
        )
