"""Append-only persistence for Phase 11M verifier receipts."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective_credential_governance import (
    GovernanceState,
    GovernedReviewAssessment,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ExternalVerificationReceipt,
    ReceiptBoundGovernanceAssessment,
    VerificationKind,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveVerifierReceiptRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def record_receipt(self, receipt: ExternalVerificationReceipt) -> bool:
        table, identity_column = {
            VerificationKind.CREDENTIAL_ISSUANCE: (
                "prospective_credential_issuances", "issuance_id",
            ),
            VerificationKind.CREDENTIAL_REVOCATION: (
                "prospective_credential_revocations", "revocation_id",
            ),
            VerificationKind.TRUSTED_TIMESTAMP: (
                "prospective_review_timestamps", "timestamp_id",
            ),
        }[receipt.kind]
        subject = json.loads(self._verified(table, identity_column, receipt.subject_id))
        if receipt.subject_hash != canonical_hash(subject):
            raise ValueError("Phase 11M verification subject does not match")
        return self._insert(
            "prospective_external_verification_receipts", "receipt_id", receipt.receipt_id,
            "INSERT OR IGNORE INTO prospective_external_verification_receipts "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (receipt.receipt_id, receipt.kind.value, receipt.subject_id, receipt.verifier_id,
             receipt.verifier_version, receipt.verified_at.isoformat(), int(receipt.accepted),
             canonical_json(receipt), canonical_hash(receipt)), canonical_hash(receipt),
        )

    def record_assessment(
        self, assessment: ReceiptBoundGovernanceAssessment,
        governance: GovernedReviewAssessment,
        receipts: tuple[ExternalVerificationReceipt, ...],
    ) -> bool:
        stored_governance = json.loads(self._verified(
            "prospective_governed_review_assessments", "assessment_id",
            assessment.governance_assessment_id,
        ))
        if (
            canonical_hash(stored_governance) != assessment.governance_assessment_hash
            or canonical_hash(governance) != assessment.governance_assessment_hash
            or governance.assessment_id != assessment.governance_assessment_id
        ):
            raise ValueError("Phase 11M governance dependency does not match")
        ordered = tuple(sorted(receipts, key=lambda item: item.receipt_id))
        if (
            tuple(item.receipt_id for item in ordered) != assessment.verification_receipt_ids
            or tuple(canonical_hash(item) for item in ordered)
            != assessment.verification_receipt_hashes
        ):
            raise ValueError("Phase 11M receipt set does not match")
        for receipt in ordered:
            self._verified(
                "prospective_external_verification_receipts", "receipt_id", receipt.receipt_id,
                canonical_hash(receipt),
            )
        return self._insert(
            "prospective_receipt_bound_governance_assessments", "assessment_id",
            assessment.assessment_id,
            "INSERT OR IGNORE INTO prospective_receipt_bound_governance_assessments "
            "VALUES (?,?,?,?,?,?,?)",
            (assessment.assessment_id, assessment.governance_assessment_id,
             assessment.review_assessment_id, assessment.evaluated_at.isoformat(),
             assessment.state.value, canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def require_verified(
        self, assessment: ReceiptBoundGovernanceAssessment,
        governance: GovernedReviewAssessment, *, as_of: datetime,
    ) -> None:
        row = self.repository.connection.execute(
            "SELECT evaluated_at,state,payload_json,payload_hash "
            "FROM prospective_receipt_bound_governance_assessments WHERE assessment_id=?",
            (assessment.assessment_id,),
        ).fetchone()
        if (
            row is None or datetime.fromisoformat(str(row[0])) > as_of
            or row[1] != GovernanceState.VERIFIED.value
            or row[2:] != (canonical_json(assessment), canonical_hash(assessment))
            or canonical_hash(json.loads(str(row[2]))) != row[3]
            or assessment.state is not GovernanceState.VERIFIED
            or assessment.governance_assessment_id != governance.assessment_id
            or assessment.governance_assessment_hash != canonical_hash(governance)
        ):
            raise ValueError(
                "verified Phase 11M receipt-bound governance is unavailable or changed"
            )

    def _verified(
        self, table: str, column: str, identity: str, expected_hash: str | None = None,
    ) -> str:
        row = self.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {column}=?", (identity,),
        ).fetchone()
        if (
            row is None or canonical_hash(json.loads(str(row[0]))) != row[1]
            or (expected_hash is not None and row[1] != expected_hash)
        ):
            raise ValueError("Phase 11M dependency is missing or corrupt")
        return str(row[0])

    def _insert(
        self, table: str, identity_column: str, identity: str, statement: str,
        values: tuple[object, ...], payload_hash: str,
    ) -> bool:
        cursor = self.repository.connection.execute(statement, values)
        if cursor.rowcount:
            self.repository.connection.commit()
            return True
        row = self.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {identity_column}=?",
            (identity,),
        ).fetchone()
        if (
            row is None or canonical_hash(json.loads(str(row[0]))) != row[1]
            or row[1] != payload_hash
        ):
            raise ValueError(f"conflicting Phase 11M record: {identity}")
        return False
