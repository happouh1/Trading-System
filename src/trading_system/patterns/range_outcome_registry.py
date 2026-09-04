"""Append-only persistence for Phase 7F entry outcomes."""

from __future__ import annotations

from datetime import UTC

from trading_system.patterns.range_outcome import RangeEntryOutcome
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class RangeOutcomeRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def persist(self, outcome: RangeEntryOutcome) -> bool:
        payload_hash = canonical_hash(outcome)
        values = (
            outcome.outcome_id, outcome.run_id, outcome.entry_id, outcome.horizon_bars,
            outcome.label_available_at.astimezone(UTC).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z"),
            canonical_json(outcome), payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_entry_outcomes
               (outcome_id, run_id, entry_id, horizon_bars, label_available_at,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT run_id, payload_hash FROM range_entry_outcomes WHERE outcome_id = ?",
                (outcome.outcome_id,),
            ).fetchone()
            if stored != (outcome.run_id, payload_hash):
                raise ValueError(f"conflicting range entry outcome: {outcome.outcome_id}")
            return False
        self.repository.connection.commit()
        return True

    def count(self, run_id: str) -> int:
        row = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_entry_outcomes WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        return int(row[0])
