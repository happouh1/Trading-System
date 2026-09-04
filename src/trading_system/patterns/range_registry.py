"""Append-only SQLite registry for Phase 7B range research evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.patterns.range_reclaim import RangeBox
from trading_system.patterns.range_research import RangeBoxOutcome, RangeResearchResult
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("database timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class RangeResearchRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def insert_box(self, run_id: str, box: RangeBox) -> bool:
        payload = canonical_json(box)
        payload_hash = canonical_hash(box)
        values = (
            box.box_id,
            run_id,
            box.symbol,
            box.timeframe.value,
            box.start_candle_id,
            box.end_candle_id,
            _time(box.known_at),
            box.parent_box_id,
            payload,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_boxes
               (box_id, run_id, symbol, timeframe, start_candle_id, end_candle_id,
                known_at, parent_box_id, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT run_id, payload_hash FROM range_boxes WHERE box_id = ?",
                (box.box_id,),
            ).fetchone()
            if stored != (run_id, payload_hash):
                raise ValueError(f"conflicting range box payload: {box.box_id}")
            return False
        self.repository.connection.commit()
        return True

    def insert_outcome(self, run_id: str, outcome: RangeBoxOutcome) -> bool:
        payload = canonical_json(outcome)
        payload_hash = canonical_hash(outcome)
        values = (
            outcome.outcome_id,
            outcome.box_id,
            run_id,
            outcome.horizon_bars,
            _time(outcome.label_available_at),
            outcome.terminal_location.value,
            payload,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_box_outcomes
               (outcome_id, box_id, run_id, horizon_bars, label_available_at,
                terminal_location, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT run_id, payload_hash FROM range_box_outcomes WHERE outcome_id = ?",
                (outcome.outcome_id,),
            ).fetchone()
            if stored != (run_id, payload_hash):
                raise ValueError(f"conflicting range outcome payload: {outcome.outcome_id}")
            return False
        self.repository.connection.commit()
        return True

    def persist(self, run_id: str, result: RangeResearchResult) -> tuple[int, int]:
        if self.repository.run_metadata(run_id) is None:
            raise ValueError("run must be persisted before range research")
        inserted_boxes = sum(self.insert_box(run_id, box) for box in result.boxes)
        inserted_outcomes = sum(
            self.insert_outcome(run_id, outcome) for outcome in result.outcomes
        )
        return inserted_boxes, inserted_outcomes

    def counts(self, run_id: str) -> tuple[int, int]:
        boxes = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_boxes WHERE run_id = ?", (run_id,)
        ).fetchone()
        outcomes = self.repository.connection.execute(
            "SELECT COUNT(*) FROM range_box_outcomes WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert boxes is not None and outcomes is not None
        return int(boxes[0]), int(outcomes[0])
