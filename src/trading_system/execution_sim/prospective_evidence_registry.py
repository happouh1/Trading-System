"""Append-only persistence for corroborated prospective input evidence."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.execution_sim.prospective_evidence import (
    CorroboratedProspectiveInputs,
    PointInTimeEvidence,
    corroborate_prospective_inputs,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveEvidenceRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def corroborate(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        portfolio_evidence: tuple[PointInTimeEvidence, PointInTimeEvidence],
        market_evidence: tuple[PointInTimeEvidence, PointInTimeEvidence],
        planned_hold_sessions: int, as_of: datetime,
    ) -> CorroboratedProspectiveInputs:
        result = corroborate_prospective_inputs(
            entry=entry, entry_assessment=entry_assessment,
            portfolio_evidence=portfolio_evidence, market_evidence=market_evidence,
            planned_hold_sessions=planned_hold_sessions,
        )
        if result.known_at > as_of:
            raise ValueError("prospective evidence unavailable at cutoff")
        connection = self.repository.connection
        connection.execute("SAVEPOINT prospective_evidence")
        try:
            for item in (*portfolio_evidence, *market_evidence):
                self._insert_evidence(item)
            payload, digest = canonical_json(result), canonical_hash(result)
            prior = connection.execute(
                "SELECT payload_json,payload_hash FROM prospective_evidence_receipts "
                "WHERE decision_id=?", (entry.decision_id,),
            ).fetchone()
            if prior is None:
                connection.execute(
                    "INSERT INTO prospective_evidence_receipts VALUES (?,?,?,?,?)",
                    (
                        entry.decision_id, result.receipt_id, result.known_at.isoformat(),
                        payload, digest,
                    ),
                )
            elif prior != (payload, digest):
                raise ValueError("prospective evidence receipt cannot be revised")
            connection.execute("RELEASE prospective_evidence")
            return result
        except Exception:
            connection.execute("ROLLBACK TO prospective_evidence")
            connection.execute("RELEASE prospective_evidence")
            raise

    def require_stored(self, result: CorroboratedProspectiveInputs, *, as_of: datetime) -> None:
        row = self.repository.connection.execute(
            "SELECT known_at,payload_json,payload_hash FROM prospective_evidence_receipts "
            "WHERE decision_id=?", (result.decision_id,),
        ).fetchone()
        payload, digest = canonical_json(result), canonical_hash(result)
        if (
            row is None or datetime.fromisoformat(str(row[0])) > as_of
            or row[1:] != (payload, digest)
            or canonical_hash(json.loads(str(row[1]))) != row[2]
        ):
            raise ValueError("corroborated prospective evidence is unavailable or changed")

    def _insert_evidence(self, item: PointInTimeEvidence) -> None:
        payload, digest = canonical_json(item), canonical_hash(item)
        prior = self.repository.connection.execute(
            "SELECT payload_json,payload_hash FROM prospective_point_in_time_evidence "
            "WHERE evidence_id=?", (item.evidence_id,),
        ).fetchone()
        if prior is None:
            self.repository.connection.execute(
                "INSERT INTO prospective_point_in_time_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (item.evidence_id, item.evidence_kind, item.source_id, item.source_authority,
                 item.source_revision, item.known_at.isoformat(), item.source_bytes_hash,
                 item.normalized_hash, item.schema_version, payload, digest),
            )
        elif prior != (payload, digest):
            raise ValueError("point-in-time evidence cannot be revised")
