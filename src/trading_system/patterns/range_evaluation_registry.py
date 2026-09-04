"""Append-only persistence for Phase 7G range evaluation evidence."""

from __future__ import annotations

from trading_system.patterns.range_evaluation import (
    RangeCohortSummary,
    RangeEvaluationAssignment,
    RangeEvaluationResult,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class RangeEvaluationRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, result: RangeEvaluationResult) -> tuple[int, int]:
        assignments = sum(self._persist_assignment(item) for item in result.assignments)
        summaries = sum(self._persist_summary(item) for item in result.summaries)
        self.repository.connection.commit()
        return assignments, summaries

    def _persist_assignment(self, item: RangeEvaluationAssignment) -> bool:
        payload_hash = canonical_hash(item)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_evaluation_assignments
               (assignment_id, plan_id, outcome_id, fold_id, partition,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item.assignment_id,
                item.plan_id,
                item.outcome_id,
                item.fold_id,
                item.partition.value,
                canonical_json(item),
                payload_hash,
            ),
        )
        if cursor.rowcount:
            return True
        stored = self.repository.connection.execute(
            """SELECT plan_id, payload_hash FROM range_evaluation_assignments
               WHERE assignment_id = ?""",
            (item.assignment_id,),
        ).fetchone()
        if stored != (item.plan_id, payload_hash):
            raise ValueError(f"conflicting Phase 7G assignment: {item.assignment_id}")
        return False

    def _persist_summary(self, item: RangeCohortSummary) -> bool:
        payload_hash = canonical_hash(item)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_cohort_summaries
               (summary_id, plan_id, fold_id, partition, gate_passed,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item.summary_id,
                item.plan_id,
                item.fold_id,
                item.partition.value,
                int(item.gate_passed),
                canonical_json(item),
                payload_hash,
            ),
        )
        if cursor.rowcount:
            return True
        stored = self.repository.connection.execute(
            "SELECT plan_id, payload_hash FROM range_cohort_summaries WHERE summary_id = ?",
            (item.summary_id,),
        ).fetchone()
        if stored != (item.plan_id, payload_hash):
            raise ValueError(f"conflicting Phase 7G summary: {item.summary_id}")
        return False

    def counts(self, plan_id: str) -> tuple[int, int]:
        assignments = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_evaluation_assignments WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        summaries = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_cohort_summaries WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        assert assignments is not None and summaries is not None
        return int(assignments[0]), int(summaries[0])
