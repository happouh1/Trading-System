"""Append-only persistence for Phase 11N signed verifier-bundle approvals."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective_verifier_approval import (
    VerifierApprovalAssessment,
    VerifierApprovalAttestation,
    VerifierApprovalCredential,
    VerifierApprovalRequest,
    VerifierApprovalState,
)
from trading_system.execution_sim.prospective_verifier_receipts import (
    ReceiptBoundGovernanceAssessment,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveVerifierApprovalRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def record_credential(self, credential: VerifierApprovalCredential) -> bool:
        return self._insert(
            "prospective_verifier_approval_credentials", "credential_id",
            credential.credential_id,
            "INSERT OR IGNORE INTO prospective_verifier_approval_credentials "
            "VALUES (?,?,?,?,?,?,?,?)",
            (credential.credential_id, credential.principal_id, credential.role,
             credential.public_key_base64, credential.valid_from.isoformat(),
             credential.valid_until.isoformat(), canonical_json(credential),
             canonical_hash(credential)),
            canonical_hash(credential),
        )

    def register_request(
        self, request: VerifierApprovalRequest,
        bound: ReceiptBoundGovernanceAssessment,
    ) -> bool:
        stored = json.loads(self._verified(
            "prospective_receipt_bound_governance_assessments", "assessment_id",
            request.receipt_bound_assessment_id,
        ))
        if (
            bound.assessment_id != request.receipt_bound_assessment_id
            or canonical_hash(bound) != request.receipt_bound_assessment_hash
            or canonical_hash(stored) != request.receipt_bound_assessment_hash
            or bound.governance_assessment_id != request.governance_assessment_id
            or bound.verification_receipt_ids != request.verification_receipt_ids
            or bound.verification_receipt_hashes != request.verification_receipt_hashes
        ):
            raise ValueError("Phase 11N receipt-bound dependency does not match")
        return self._insert(
            "prospective_verifier_approval_requests", "request_id", request.request_id,
            "INSERT OR IGNORE INTO prospective_verifier_approval_requests "
            "VALUES (?,?,?,?,?,?,?,?)",
            (request.request_id, request.receipt_bound_assessment_id,
             request.requested_at.isoformat(), request.valid_from.isoformat(),
             request.valid_until.isoformat(), request.request_hash,
             canonical_json(request), canonical_hash(request)),
            canonical_hash(request),
        )

    def record_attestation(self, attestation: VerifierApprovalAttestation) -> bool:
        request = json.loads(self._verified(
            "prospective_verifier_approval_requests", "request_id", attestation.request_id,
        ))
        credential = json.loads(self._verified(
            "prospective_verifier_approval_credentials", "credential_id",
            attestation.credential_id,
        ))
        if (
            request.get("request_hash") != attestation.request_hash
            or credential.get("principal_id") != attestation.principal_id
            or credential.get("role") != attestation.role
        ):
            raise ValueError("Phase 11N attestation dependency does not match")
        return self._insert(
            "prospective_verifier_approval_attestations", "attestation_id",
            attestation.attestation_id,
            "INSERT OR IGNORE INTO prospective_verifier_approval_attestations "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (attestation.attestation_id, attestation.request_id,
             attestation.credential_id, attestation.principal_id, attestation.role,
             attestation.signed_at.isoformat(), attestation.signature_base64,
             canonical_json(attestation), canonical_hash(attestation)),
            canonical_hash(attestation),
        )

    def record_assessment(self, assessment: VerifierApprovalAssessment) -> bool:
        request = json.loads(self._verified(
            "prospective_verifier_approval_requests", "request_id", assessment.request_id,
        ))
        if (
            request.get("request_hash") != assessment.request_hash
            or request.get("config_hash") != assessment.config_hash
            or request.get("receipt_bound_assessment_id")
            != assessment.receipt_bound_assessment_id
        ):
            raise ValueError("Phase 11N approval request does not match")
        return self._insert(
            "prospective_verifier_approval_assessments", "assessment_id",
            assessment.assessment_id,
            "INSERT OR IGNORE INTO prospective_verifier_approval_assessments "
            "VALUES (?,?,?,?,?,?,?,?)",
            (assessment.assessment_id, assessment.request_id,
             assessment.receipt_bound_assessment_id, assessment.evaluated_at.isoformat(),
             assessment.state.value, assessment.request_hash,
             canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def require_approved(
        self, assessment: VerifierApprovalAssessment,
        bound: ReceiptBoundGovernanceAssessment, *, as_of: datetime,
    ) -> None:
        row = self.repository.connection.execute(
            "SELECT evaluated_at,state,payload_json,payload_hash "
            "FROM prospective_verifier_approval_assessments WHERE assessment_id=?",
            (assessment.assessment_id,),
        ).fetchone()
        if (
            row is None or datetime.fromisoformat(str(row[0])) > as_of
            or row[1] != VerifierApprovalState.APPROVED.value
            or row[2:] != (canonical_json(assessment), canonical_hash(assessment))
            or canonical_hash(json.loads(str(row[2]))) != row[3]
            or assessment.state is not VerifierApprovalState.APPROVED
            or assessment.receipt_bound_assessment_id != bound.assessment_id
        ):
            raise ValueError("approved Phase 11N verifier bundle is unavailable or changed")

    def _verified(self, table: str, column: str, identity: str) -> str:
        row = self.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {column}=?", (identity,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[0]))) != row[1]:
            raise ValueError("Phase 11N dependency is missing or corrupt")
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
            raise ValueError(f"conflicting Phase 11N record: {identity}")
        return False
