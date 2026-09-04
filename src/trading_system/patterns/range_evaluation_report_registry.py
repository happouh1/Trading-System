"""Append-only persistence for Phase 7H range evaluation reports."""

from __future__ import annotations

from trading_system.patterns.range_evaluation import RangeEvaluationResult
from trading_system.patterns.range_evaluation_report import RangeEvaluationReport
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class RangeEvaluationReportRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, report: RangeEvaluationReport, result: RangeEvaluationResult) -> bool:
        assignments = tuple(sorted(result.assignments, key=lambda item: item.assignment_id))
        summaries = tuple(sorted(result.summaries, key=lambda item: item.summary_id))
        if canonical_hash(assignments) != report.assignment_root:
            raise ValueError("Phase 7H assignment root does not match supplied evidence")
        if canonical_hash(summaries) != report.summary_root:
            raise ValueError("Phase 7H summary root does not match supplied evidence")
        for assignment in assignments:
            self._require_source(
                "range_evaluation_assignments",
                "assignment_id",
                assignment.assignment_id,
                report.plan_id,
                canonical_hash(assignment),
            )
        for summary in summaries:
            self._require_source(
                "range_cohort_summaries",
                "summary_id",
                summary.summary_id,
                report.plan_id,
                canonical_hash(summary),
            )
        payload_hash = canonical_hash(report)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_evaluation_reports
               (report_id, plan_id, assignment_root, summary_root, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report.report_id,
                report.plan_id,
                report.assignment_root,
                report.summary_root,
                canonical_json(report),
                payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                "SELECT plan_id, payload_hash FROM range_evaluation_reports WHERE report_id = ?",
                (report.report_id,),
            ).fetchone()
            if stored != (report.plan_id, payload_hash):
                raise ValueError(f"conflicting Phase 7H report: {report.report_id}")
            return False
        self.repository.connection.commit()
        return True

    def _require_source(
        self,
        table: str,
        identity_column: str,
        identity: str,
        plan_id: str,
        payload_hash: str,
    ) -> None:
        row = self.repository.connection.execute(
            f"SELECT plan_id, payload_hash FROM {table} WHERE {identity_column} = ?",
            (identity,),
        ).fetchone()
        if row != (plan_id, payload_hash):
            raise ValueError(f"missing or corrupt Phase 7G evidence: {identity}")

    def count(self, plan_id: str) -> int:
        row = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_evaluation_reports WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        assert row is not None
        return int(row[0])
