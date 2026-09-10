"""Append-only persistence for Phase 9F sandbox supervision leases."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.paper.sandbox_lease import (
    SandboxLeaseAssessment,
    SandboxLeaseRevocation,
    SandboxStageLease,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class SandboxLeaseRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def register_lease(self, lease: SandboxStageLease) -> bool:
        authorization = self.repository.connection.execute(
            """SELECT a.state, a.payload_json, a.payload_hash, r.session_id,
                      a.plan_id, a.stage_id
               FROM paper_stage_authorization_assessments AS a
               JOIN paper_stage_authorization_requests AS r ON r.request_id = a.request_id
               WHERE a.assessment_id = ?""",
            (lease.authorization_assessment_id,),
        ).fetchone()
        plan = self.repository.connection.execute(
            """SELECT plan_hash, payload_json, payload_hash, session_id
               FROM paper_staged_rollout_plans WHERE plan_id = ?""",
            (lease.plan_id,),
        ).fetchone()
        if (
            authorization is None
            or str(authorization[0]) != "SIGNATURES_VERIFIED"
            or canonical_hash(json.loads(str(authorization[1]))) != str(authorization[2])
            or str(authorization[2]) != lease.authorization_assessment_hash
            or str(authorization[3]) != lease.session_id
            or str(authorization[4]) != lease.plan_id
            or str(authorization[5]) != lease.stage_id
            or plan is None
            or str(plan[0]) != lease.plan_hash
            or canonical_hash(json.loads(str(plan[1]))) != str(plan[2])
            or str(plan[3]) != lease.session_id
        ):
            raise ValueError("Phase 9F lease dependency is missing, ineligible, or corrupt")
        return self._insert(
            "paper_sandbox_stage_leases", "lease_id", lease.lease_id,
            """INSERT OR IGNORE INTO paper_sandbox_stage_leases
               (lease_id, session_id, authorization_assessment_id, plan_id, stage_id,
                issued_at, valid_from, valid_until, lease_hash, config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lease.lease_id, lease.session_id, lease.authorization_assessment_id,
             lease.plan_id, lease.stage_id, _time(lease.issued_at), _time(lease.valid_from),
             _time(lease.valid_until), lease.lease_hash, lease.config_hash,
             canonical_json(lease), canonical_hash(lease)), canonical_hash(lease),
        )

    def record_revocation(self, revocation: SandboxLeaseRevocation) -> bool:
        lease_hash = self._verified_lease(revocation.lease_id)
        if lease_hash != revocation.lease_hash:
            raise ValueError("Phase 9F lease hash does not match")
        return self._insert(
            "paper_sandbox_lease_revocations", "revocation_id", revocation.revocation_id,
            """INSERT OR IGNORE INTO paper_sandbox_lease_revocations
               (revocation_id, lease_id, revoked_at, reason_code, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (revocation.revocation_id, revocation.lease_id, _time(revocation.revoked_at),
             revocation.reason_code, canonical_json(revocation), canonical_hash(revocation)),
            canonical_hash(revocation),
        )

    def record_assessment(
        self,
        assessment: SandboxLeaseAssessment,
        *,
        revocation_id: str | None = None,
    ) -> bool:
        lease_hash = self._verified_lease(assessment.lease_id)
        if lease_hash != assessment.lease_hash:
            raise ValueError("Phase 9F lease hash does not match")
        if assessment.revocation_hash is None:
            if revocation_id is not None:
                raise ValueError("Phase 9F assessment unexpectedly references revocation")
        else:
            row = self.repository.connection.execute(
                """SELECT lease_id, payload_json, payload_hash
                   FROM paper_sandbox_lease_revocations WHERE revocation_id = ?""",
                (revocation_id,),
            ).fetchone()
            if (
                row is None
                or str(row[0]) != assessment.lease_id
                or canonical_hash(json.loads(str(row[1]))) != str(row[2])
                or str(row[2]) != assessment.revocation_hash
            ):
                raise ValueError("Phase 9F revocation dependency is missing or corrupt")
        return self._insert(
            "paper_sandbox_lease_assessments", "assessment_id", assessment.assessment_id,
            """INSERT OR IGNORE INTO paper_sandbox_lease_assessments
               (assessment_id, lease_id, revocation_id, evaluated_at, state,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (assessment.assessment_id, assessment.lease_id, revocation_id,
             _time(assessment.evaluated_at), assessment.state.value,
             canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def _verified_lease(self, lease_id: str) -> str:
        row = self.repository.connection.execute(
            """SELECT lease_hash, payload_json, payload_hash
               FROM paper_sandbox_stage_leases WHERE lease_id = ?""",
            (lease_id,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[1]))) != str(row[2]):
            raise ValueError("Phase 9F lease dependency is missing or corrupt")
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
                raise ValueError(f"conflicting Phase 9F record: {identity}")
            return False
        self.repository.connection.commit()
        return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 9F timestamp must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
