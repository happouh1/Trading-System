"""Append-only persistence for Phase 7E hypothetical entries."""

from __future__ import annotations

from datetime import UTC

from trading_system.patterns.range_entry import RangeResearchEntry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class RangeEntryRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, entry: RangeResearchEntry) -> bool:
        payload_hash = canonical_hash(entry)
        values = (
            entry.entry_id,
            entry.run_id,
            entry.evidence_id,
            entry.source_candle_id,
            entry.entry_time.astimezone(UTC).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            entry.status.value,
            canonical_json(entry),
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_research_entries
               (entry_id, run_id, evidence_id, source_candle_id, entry_time, status,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT run_id, payload_hash FROM range_research_entries WHERE entry_id = ?",
                (entry.entry_id,),
            ).fetchone()
            if stored != (entry.run_id, payload_hash):
                raise ValueError(f"conflicting range research entry: {entry.entry_id}")
            return False
        self.repository.connection.commit()
        return True

    def count(self, run_id: str) -> int:
        row = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_research_entries WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        return int(row[0])
