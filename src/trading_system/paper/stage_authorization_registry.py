"""Append-only persistence for Phase 9E signed stage-review evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.paper.stage_authorization import (
    StageAuthorizationAssessment,
    StageAuthorizationRequest,
    StageReviewAttestation,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class StageAuthorizationRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def register_request(self, request: StageAuthorizationRequest) -> bool:
        dependency = self.repository.connection.execute(
            """SELECT a.state, a.payload_json, a.payload_hash, p.session_id
               FROM paper_rollout_gate_assessments AS a
               JOIN paper_staged_rollout_plans AS p ON p.plan_id = a.plan_id
               WHERE a.assessment_id = ?""",
            (request.rollout_assessment_id,),
        ).fetchone()
        if (
            dependency is None
            or str(dependency[0]) != "READY_FOR_HUMAN_REVIEW"
            or canonical_hash(json.loads(str(dependency[1]))) != str(dependency[2])
            or str(dependency[2]) != request.rollout_assessment_hash
            or str(dependency[3]) != request.session_id
        ):
            raise ValueError("Phase 9E rollout dependency is missing, ineligible, or corrupt")
        return self._insert(
            "paper_stage_authorization_requests", "request_id", request.request_id,
            """INSERT OR IGNORE INTO paper_stage_authorization_requests
               (request_id, session_id, rollout_assessment_id, plan_id, stage_id,
                requested_at, valid_from, valid_until, request_hash, config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.request_id, request.session_id, request.rollout_assessment_id,
             request.plan_id, request.stage_id, _time(request.requested_at),
             _time(request.valid_from), _time(request.valid_until), request.request_hash,
             request.config_hash, canonical_json(request), canonical_hash(request)),
            canonical_hash(request),
        )

    def record_attestation(self, attestation: StageReviewAttestation) -> bool:
        request_hash = self._verified_request(attestation.request_id)
        if request_hash != attestation.request_hash:
            raise ValueError("Phase 9E request hash does not match")
        return self._insert(
            "paper_stage_review_attestations", "attestation_id", attestation.attestation_id,
            """INSERT OR IGNORE INTO paper_stage_review_attestations
               (attestation_id, request_id, credential_id, principal_id, role, signed_at,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (attestation.attestation_id, attestation.request_id, attestation.credential_id,
             attestation.principal_id, attestation.role, _time(attestation.signed_at),
             canonical_json(attestation), canonical_hash(attestation)),
            canonical_hash(attestation),
        )

    def record_assessment(self, assessment: StageAuthorizationAssessment) -> bool:
        request_hash = self._verified_request(assessment.request_id)
        if request_hash != assessment.request_hash:
            raise ValueError("Phase 9E request hash does not match")
        return self._insert(
            "paper_stage_authorization_assessments", "assessment_id", assessment.assessment_id,
            """INSERT OR IGNORE INTO paper_stage_authorization_assessments
               (assessment_id, request_id, plan_id, stage_id, evaluated_at, state,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (assessment.assessment_id, assessment.request_id, assessment.plan_id,
             assessment.stage_id, _time(assessment.evaluated_at), assessment.state.value,
             canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def _verified_request(self, request_id: str) -> str:
        row = self.repository.connection.execute(
            """SELECT request_hash, payload_json, payload_hash
               FROM paper_stage_authorization_requests WHERE request_id = ?""",
            (request_id,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[1]))) != str(row[2]):
            raise ValueError("Phase 9E request dependency is missing or corrupt")
        return str(row[0])

    def _insert(
        self, table: str, identity_column: str, identity: str, statement: str,
        values: tuple[object, ...], payload_hash: str,
    ) -> bool:
        cursor = self.repository.connection.execute(statement, values)
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                f"SELECT payload_json, payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if (
                row is None
                or canonical_hash(json.loads(str(row[0]))) != str(row[1])
                or str(row[1]) != payload_hash
            ):
                raise ValueError(f"conflicting Phase 9E record: {identity}")
            return False
        self.repository.connection.commit()
        return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 9E timestamp must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
