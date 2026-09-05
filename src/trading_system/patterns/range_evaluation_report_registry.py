"""Append-only persistence for Phase 7H range evaluation reports."""

from __future__ import annotations

import json
from collections.abc import Mapping

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
        inserted = bool(cursor.rowcount)
        if not inserted:
            stored = self.repository.connection.execute(
                "SELECT plan_id, payload_hash FROM range_evaluation_reports WHERE report_id = ?",
                (report.report_id,),
            ).fetchone()
            if stored != (report.plan_id, payload_hash):
                raise ValueError(f"conflicting Phase 7H report: {report.report_id}")
        self._persist_members(
            report.report_id,
            "ASSIGNMENT",
            tuple((item.assignment_id, canonical_hash(item)) for item in assignments),
        )
        self._persist_members(
            report.report_id,
            "SUMMARY",
            tuple((item.summary_id, canonical_hash(item)) for item in summaries),
        )
        self.repository.connection.commit()
        return inserted

    def _persist_members(
        self,
        report_id: str,
        member_type: str,
        members: tuple[tuple[str, str], ...],
    ) -> None:
        for ordinal, (source_id, source_hash) in enumerate(members):
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO range_evaluation_report_members
                   (report_id, member_type, ordinal, source_id, source_payload_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (report_id, member_type, ordinal, source_id, source_hash),
            )
            if cursor.rowcount:
                continue
            stored = self.repository.connection.execute(
                """SELECT source_id, source_payload_hash
                   FROM range_evaluation_report_members
                   WHERE report_id = ? AND member_type = ? AND ordinal = ?""",
                (report_id, member_type, ordinal),
            ).fetchone()
            if stored != (source_id, source_hash):
                raise ValueError(f"conflicting Phase 7I report member: {source_id}")

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

    def load_verified_payloads(
        self, report_id: str
    ) -> tuple[Mapping[str, object], tuple[Mapping[str, object], ...]]:
        report, _assignments, summaries = self.load_verified_evidence(report_id)
        return report, summaries

    def load_verified_evidence(
        self, report_id: str
    ) -> tuple[
        Mapping[str, object],
        tuple[Mapping[str, object], ...],
        tuple[Mapping[str, object], ...],
    ]:
        report_row = self.repository.connection.execute(
            """SELECT plan_id, assignment_root, summary_root, payload_json, payload_hash
               FROM range_evaluation_reports WHERE report_id = ?""",
            (report_id,),
        ).fetchone()
        if report_row is None:
            raise ValueError(f"unknown Phase 7H report: {report_id}")
        report_payload = _object(str(report_row[3]), "report")
        if canonical_hash(report_payload) != str(report_row[4]):
            raise ValueError("stored Phase 7H report payload is corrupt")
        assignments = self._load_members(report_id, "ASSIGNMENT")
        summaries = self._load_members(report_id, "SUMMARY")
        if canonical_hash(assignments) != str(report_row[1]):
            raise ValueError("stored Phase 7I assignment membership root is corrupt")
        if canonical_hash(summaries) != str(report_row[2]):
            raise ValueError("stored Phase 7I summary membership root is corrupt")
        if report_payload.get("report_id") != report_id:
            raise ValueError("stored Phase 7H report identity is corrupt")
        if report_payload.get("plan_id") != str(report_row[0]):
            raise ValueError("stored Phase 7H report plan is corrupt")
        return report_payload, assignments, summaries

    def _load_members(
        self, report_id: str, member_type: str
    ) -> tuple[Mapping[str, object], ...]:
        table, identity_column = (
            ("range_evaluation_assignments", "assignment_id")
            if member_type == "ASSIGNMENT"
            else ("range_cohort_summaries", "summary_id")
        )
        rows = self.repository.connection.execute(
            """SELECT ordinal, source_id, source_payload_hash
               FROM range_evaluation_report_members
               WHERE report_id = ? AND member_type = ? ORDER BY ordinal""",
            (report_id, member_type),
        ).fetchall()
        if not rows or [int(row[0]) for row in rows] != list(range(len(rows))):
            raise ValueError(f"Phase 7I {member_type.lower()} membership is incomplete")
        result: list[Mapping[str, object]] = []
        for _ordinal, source_id, expected_hash in rows:
            source = self.repository.connection.execute(
                f"SELECT payload_json, payload_hash FROM {table} WHERE {identity_column} = ?",
                (str(source_id),),
            ).fetchone()
            if source is None or str(source[1]) != str(expected_hash):
                raise ValueError(f"missing or corrupt Phase 7G report member: {source_id}")
            payload = _object(str(source[0]), member_type.lower())
            if canonical_hash(payload) != str(expected_hash):
                raise ValueError(f"corrupt Phase 7G report member payload: {source_id}")
            result.append(payload)
        return tuple(result)


def _object(payload_json: str, name: str) -> Mapping[str, object]:
    value = json.loads(payload_json)
    if not isinstance(value, dict):
        raise ValueError(f"stored Phase 7I {name} payload must be an object")
    return value
