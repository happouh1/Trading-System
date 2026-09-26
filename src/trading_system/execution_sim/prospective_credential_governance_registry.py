"""Append-only registry for Phase 11L credential governance evidence."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective_credential_governance import (
    CredentialIssuance,
    CredentialRevocation,
    GovernanceState,
    GovernedReviewAssessment,
    TrustedTimestampEvidence,
)
from trading_system.execution_sim.prospective_evidence_review import EvidenceReviewAssessment
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveCredentialGovernanceRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def record_issuance(self, issuance: CredentialIssuance) -> bool:
        self._verified(
            "prospective_evidence_review_credentials", "credential_id", issuance.credential_id,
            issuance.credential_hash,
        )
        return self._insert(
            "prospective_credential_issuances", "issuance_id", issuance.issuance_id,
            "INSERT OR IGNORE INTO prospective_credential_issuances VALUES (?,?,?,?,?,?,?)",
            (issuance.issuance_id, issuance.issuer_id, issuance.credential_id,
             issuance.issued_at.isoformat(), issuance.supersedes_credential_id,
             canonical_json(issuance), canonical_hash(issuance)), canonical_hash(issuance),
        )

    def record_revocation(self, revocation: CredentialRevocation) -> bool:
        issuance = json.loads(self._verified(
            "prospective_credential_issuances", "credential_id", revocation.credential_id,
        ))
        if (
            issuance["issuer_id"] != revocation.issuer_id
            or issuance["credential_hash"] != revocation.credential_hash
        ):
            raise ValueError("Phase 11L revocation dependency does not match")
        return self._insert(
            "prospective_credential_revocations", "revocation_id", revocation.revocation_id,
            "INSERT OR IGNORE INTO prospective_credential_revocations VALUES (?,?,?,?,?,?,?)",
            (revocation.revocation_id, revocation.issuer_id, revocation.credential_id,
             revocation.revoked_at.isoformat(), revocation.reason_code,
             canonical_json(revocation), canonical_hash(revocation)), canonical_hash(revocation),
        )

    def record_timestamp(self, timestamp: TrustedTimestampEvidence) -> bool:
        self._verified(
            "prospective_evidence_review_attestations", "attestation_id",
            timestamp.attestation_id, timestamp.attestation_hash,
        )
        return self._insert(
            "prospective_review_timestamps", "timestamp_id", timestamp.timestamp_id,
            "INSERT OR IGNORE INTO prospective_review_timestamps VALUES (?,?,?,?,?,?,?)",
            (timestamp.timestamp_id, timestamp.provider_id, timestamp.attestation_id,
             timestamp.timestamped_at.isoformat(), timestamp.received_at.isoformat(),
             canonical_json(timestamp), canonical_hash(timestamp)), canonical_hash(timestamp),
        )

    def record_assessment(
        self, assessment: GovernedReviewAssessment, review: EvidenceReviewAssessment,
    ) -> bool:
        review_json = json.loads(self._verified(
            "prospective_evidence_review_assessments", "assessment_id",
            assessment.review_assessment_id,
        ))
        if (
            review.assessment_id != assessment.review_assessment_id
            or canonical_hash(review) != canonical_hash(review_json)
        ):
            raise ValueError("Phase 11L review assessment dependency does not match")
        return self._insert(
            "prospective_governed_review_assessments", "assessment_id",
            assessment.assessment_id,
            "INSERT OR IGNORE INTO prospective_governed_review_assessments VALUES (?,?,?,?,?,?)",
            (assessment.assessment_id, assessment.review_assessment_id,
             assessment.evaluated_at.isoformat(), assessment.state.value,
             canonical_json(assessment), canonical_hash(assessment)), canonical_hash(assessment),
        )

    def require_verified(
        self, assessment: GovernedReviewAssessment, review: EvidenceReviewAssessment, *,
        as_of: datetime,
    ) -> None:
        row = self.repository.connection.execute(
            "SELECT evaluated_at,state,payload_json,payload_hash "
            "FROM prospective_governed_review_assessments WHERE assessment_id=?",
            (assessment.assessment_id,),
        ).fetchone()
        if (
            row is None or datetime.fromisoformat(str(row[0])) > as_of
            or row[1] != GovernanceState.VERIFIED.value
            or row[2:] != (canonical_json(assessment), canonical_hash(assessment))
            or canonical_hash(json.loads(str(row[2]))) != row[3]
            or assessment.state is not GovernanceState.VERIFIED
            or assessment.review_assessment_id != review.assessment_id
        ):
            raise ValueError("verified Phase 11L governance is unavailable or changed")

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
            raise ValueError("Phase 11L dependency is missing or corrupt")
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
            raise ValueError(f"conflicting Phase 11L record: {identity}")
        return False
