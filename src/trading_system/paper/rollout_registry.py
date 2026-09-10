"""Append-only persistence for Phase 9D staged-rollout review artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.paper.rollout import (
    RolloutGateAssessment,
    RolloutStageEvidence,
    StagedRolloutPlan,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class PaperRolloutRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def register_plan(self, plan: StagedRolloutPlan) -> bool:
        dependency = self.repository.connection.execute(
            """SELECT a.state, a.payload_json, a.payload_hash, d.session_id
               FROM paper_certification_assessments AS a
               JOIN paper_certification_dossiers AS d ON d.dossier_id = a.dossier_id
               WHERE a.assessment_id = ?""",
            (plan.certification_assessment_id,),
        ).fetchone()
        if (
            dependency is None
            or str(dependency[0]) != "REVIEW_READY"
            or canonical_hash(json.loads(str(dependency[1]))) != str(dependency[2])
            or str(dependency[2]) != plan.certification_assessment_hash
            or str(dependency[3]) != plan.session_id
        ):
            raise ValueError("Phase 9D certification dependency is missing, ineligible, or corrupt")
        inserted = self._insert(
            "paper_staged_rollout_plans", "plan_id", plan.plan_id,
            """INSERT OR IGNORE INTO paper_staged_rollout_plans
               (plan_id, session_id, certification_assessment_id, declared_at, plan_hash,
                config_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan.plan_id, plan.session_id, plan.certification_assessment_id,
             _time(plan.declared_at), plan.plan_hash, plan.config_hash,
             canonical_json(plan), canonical_hash(plan)), canonical_hash(plan), commit=False,
        )
        if inserted:
            for stage in plan.stages:
                self.repository.connection.execute(
                    """INSERT INTO paper_rollout_stages
                       (plan_id, stage_id, sequence, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (plan.plan_id, stage.stage_id, stage.sequence,
                     canonical_json(stage), canonical_hash(stage)),
                )
            self.repository.connection.commit()
        else:
            stored = self.repository.connection.execute(
                """SELECT stage_id, payload_json, payload_hash FROM paper_rollout_stages
                   WHERE plan_id = ? ORDER BY sequence""",
                (plan.plan_id,),
            ).fetchall()
            expected = [
                (stage.stage_id, canonical_json(stage), canonical_hash(stage))
                for stage in plan.stages
            ]
            if [tuple(map(str, row)) for row in stored] != expected:
                raise ValueError(f"conflicting Phase 9D stages: {plan.plan_id}")
        return inserted

    def record_evidence(self, evidence: RolloutStageEvidence) -> bool:
        self._verified_plan(evidence.plan_id)
        stage = self.repository.connection.execute(
            "SELECT 1 FROM paper_rollout_stages WHERE plan_id = ? AND stage_id = ?",
            (evidence.plan_id, evidence.stage_id),
        ).fetchone()
        if stage is None:
            raise ValueError("Phase 9D stage dependency is missing")
        return self._insert(
            "paper_rollout_stage_evidence", "evidence_id", evidence.evidence_id,
            """INSERT OR IGNORE INTO paper_rollout_stage_evidence
               (evidence_id, plan_id, stage_id, observed_at, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (evidence.evidence_id, evidence.plan_id, evidence.stage_id,
             _time(evidence.observed_at), canonical_json(evidence), canonical_hash(evidence)),
            canonical_hash(evidence),
        )

    def record_assessment(
        self, assessment: RolloutGateAssessment, evidence_id: str
    ) -> bool:
        plan_hash = self._verified_plan(assessment.plan_id)
        evidence = self.repository.connection.execute(
            """SELECT plan_id, stage_id, payload_json, payload_hash
               FROM paper_rollout_stage_evidence WHERE evidence_id = ?""",
            (evidence_id,),
        ).fetchone()
        if (
            evidence is None
            or str(evidence[0]) != assessment.plan_id
            or str(evidence[1]) != assessment.stage_id
            or canonical_hash(json.loads(str(evidence[2]))) != str(evidence[3])
            or str(evidence[3]) != assessment.evidence_hash
            or plan_hash != assessment.plan_hash
        ):
            raise ValueError("Phase 9D evidence dependency is missing or corrupt")
        return self._insert(
            "paper_rollout_gate_assessments", "assessment_id", assessment.assessment_id,
            """INSERT OR IGNORE INTO paper_rollout_gate_assessments
               (assessment_id, plan_id, stage_id, evidence_id, evaluated_at, state,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (assessment.assessment_id, assessment.plan_id, assessment.stage_id, evidence_id,
             _time(assessment.evaluated_at), assessment.state.value,
             canonical_json(assessment), canonical_hash(assessment)),
            canonical_hash(assessment),
        )

    def _verified_plan(self, plan_id: str) -> str:
        row = self.repository.connection.execute(
            """SELECT plan_hash, payload_json, payload_hash
               FROM paper_staged_rollout_plans WHERE plan_id = ?""",
            (plan_id,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(str(row[1]))) != str(row[2]):
            raise ValueError("Phase 9D plan dependency is missing or corrupt")
        return str(row[0])

    def _insert(
        self, table: str, identity_column: str, identity: str, statement: str,
        values: tuple[object, ...], payload_hash: str, *, commit: bool = True,
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
                raise ValueError(f"conflicting Phase 9D record: {identity}")
            return False
        if commit:
            self.repository.connection.commit()
        return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 9D timestamp must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
