"""Append-only persistence for Phase 7D causal range-reclaim evidence."""

from __future__ import annotations

from datetime import UTC

from trading_system.patterns.range_trigger import RangeReclaimEvidence
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class RangeTriggerRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, evidence: RangeReclaimEvidence) -> bool:
        payload_hash = canonical_hash(evidence)
        values = (
            evidence.evidence_id,
            evidence.run_id,
            evidence.box_id,
            evidence.event_id,
            evidence.known_at.astimezone(UTC).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            evidence.direction.value,
            evidence.boundary.value,
            canonical_json(evidence),
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_reclaim_evidence
               (evidence_id, run_id, box_id, event_id, known_at, direction, boundary,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT run_id, payload_hash FROM range_reclaim_evidence WHERE evidence_id = ?",
                (evidence.evidence_id,),
            ).fetchone()
            if stored != (evidence.run_id, payload_hash):
                raise ValueError(f"conflicting range-reclaim evidence: {evidence.evidence_id}")
            return False
        self.repository.connection.commit()
        return True

    def count(self, run_id: str) -> int:
        row = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_reclaim_evidence WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        return int(row[0])
