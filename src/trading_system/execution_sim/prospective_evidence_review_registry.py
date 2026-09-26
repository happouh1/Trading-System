"""Append-only registry for Phase 11K signed evidence review."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective_evidence import CorroboratedProspectiveInputs
from trading_system.execution_sim.prospective_evidence_review import (
    EvidenceReviewAssessment,
    EvidenceReviewAttestation,
    EvidenceReviewCredential,
    EvidenceReviewRequest,
    EvidenceReviewState,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveEvidenceReviewRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def record_credential(self, credential: EvidenceReviewCredential) -> bool:
        return self._insert(
            "prospective_evidence_review_credentials", "credential_id", credential.credential_id,
            "INSERT OR IGNORE INTO prospective_evidence_review_credentials "
            "VALUES (?,?,?,?,?,?,?,?)",
            (credential.credential_id, credential.principal_id, credential.role,
             credential.public_key_base64, credential.valid_from.isoformat(),
             credential.valid_until.isoformat(), canonical_json(credential),
             canonical_hash(credential)), canonical_hash(credential),
        )

    def register_request(
        self, request: EvidenceReviewRequest, evidence: CorroboratedProspectiveInputs,
    ) -> bool:
        row = self.repository.connection.execute(
            "SELECT receipt_id,payload_json,payload_hash FROM prospective_evidence_receipts "
            "WHERE decision_id=?", (request.decision_id,),
        ).fetchone()
        if (
            row is None or row[0] != request.receipt_id
            or canonical_hash(json.loads(str(row[1]))) != row[2]
            or row[2] != request.receipt_hash
            or canonical_hash(evidence) != request.receipt_hash
            or evidence.receipt_id != request.receipt_id
        ):
            raise ValueError("Phase 11K evidence receipt dependency is missing or corrupt")
        return self._insert(
            "prospective_evidence_review_requests", "request_id", request.request_id,
            "INSERT OR IGNORE INTO prospective_evidence_review_requests VALUES (?,?,?,?,?,?,?,?,?)",
            (request.request_id, request.decision_id, request.receipt_id,
             request.requested_at.isoformat(), request.valid_from.isoformat(),
             request.valid_until.isoformat(), request.request_hash, canonical_json(request),
             canonical_hash(request)), canonical_hash(request),
        )

    def record_attestation(self, attestation: EvidenceReviewAttestation) -> bool:
        request = self._verified(
            "prospective_evidence_review_requests", "request_id", attestation.request_id,
        )
        credential = self._verified(
            "prospective_evidence_review_credentials", "credential_id", attestation.credential_id,
        )
        if (
            json.loads(request)["request_hash"] != attestation.request_hash
            or json.loads(credential)["principal_id"] != attestation.principal_id
        ):
            raise ValueError("Phase 11K attestation dependency does not match")
        return self._insert(
            "prospective_evidence_review_attestations", "attestation_id",
            attestation.attestation_id,
            "INSERT OR IGNORE INTO prospective_evidence_review_attestations "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (attestation.attestation_id, attestation.request_id, attestation.credential_id,
             attestation.principal_id, attestation.role, attestation.signed_at.isoformat(),
             attestation.signature_base64, canonical_json(attestation),
             canonical_hash(attestation)),
            canonical_hash(attestation),
        )

    def record_assessment(self, assessment: EvidenceReviewAssessment) -> bool:
        request = json.loads(self._verified(
            "prospective_evidence_review_requests", "request_id", assessment.request_id,
        ))
        if (
            request["request_hash"] != assessment.request_hash
            or request["receipt_hash"] != assessment.receipt_hash
            or request["receipt_id"] != assessment.receipt_id
        ):
            raise ValueError("Phase 11K assessment dependency does not match")
        return self._insert(
            "prospective_evidence_review_assessments", "assessment_id", assessment.assessment_id,
            "INSERT OR IGNORE INTO prospective_evidence_review_assessments "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (assessment.assessment_id, assessment.request_id, assessment.decision_id,
             assessment.receipt_id, assessment.evaluated_at.isoformat(), assessment.state.value,
             assessment.request_hash, canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def require_verified(
        self, assessment: EvidenceReviewAssessment,
        evidence: CorroboratedProspectiveInputs, *, as_of: datetime,
    ) -> None:
        row = self.repository.connection.execute(
            "SELECT evaluated_at,state,payload_json,payload_hash "
            "FROM prospective_evidence_review_assessments WHERE assessment_id=?",
            (assessment.assessment_id,),
        ).fetchone()
        if (
            row is None or datetime.fromisoformat(str(row[0])) > as_of
            or row[1] != EvidenceReviewState.SIGNATURES_VERIFIED.value
            or row[2:] != (canonical_json(assessment), canonical_hash(assessment))
            or canonical_hash(json.loads(str(row[2]))) != row[3]
            or assessment.state is not EvidenceReviewState.SIGNATURES_VERIFIED
            or assessment.receipt_id != evidence.receipt_id
            or assessment.receipt_hash != canonical_hash(evidence)
        ):
            raise ValueError("verified Phase 11K review is unavailable or changed")

    def _verified(self, table: str, column: str, identity: str) -> str:
        row = self.repository.connection.execute(
            f"SELECT payload_json,payload_hash FROM {table} WHERE {column}=?", (identity,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[0]))) != row[1]:
            raise ValueError("Phase 11K dependency is missing or corrupt")
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
            raise ValueError(f"conflicting Phase 11K record: {identity}")
        return False
