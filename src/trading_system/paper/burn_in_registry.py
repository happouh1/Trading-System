"""Append-only Phase 9B paper burn-in protocol and assessment storage."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.paper.burn_in import PaperBurnInAssessment, PaperBurnInProtocol
from trading_system.paper.operator_control import PaperOperatorSnapshot
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class PaperBurnInRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def register(self, protocol: PaperBurnInProtocol) -> bool:
        session = self.repository.connection.execute(
            "SELECT created_at FROM paper_sessions WHERE session_id = ?",
            (protocol.session_id,),
        ).fetchone()
        if session is None:
            raise ValueError("Phase 9B paper session does not exist")
        return self._insert(
            "paper_burn_in_protocols",
            "protocol_id",
            protocol.protocol_id,
            """INSERT OR IGNORE INTO paper_burn_in_protocols
               (protocol_id, session_id, declared_at, window_start, window_end,
                definition_hash, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                protocol.protocol_id,
                protocol.session_id,
                _time(protocol.declared_at),
                _time(protocol.window_start),
                _time(protocol.window_end),
                protocol.definition_hash,
                protocol.config_hash,
                canonical_json(protocol),
                canonical_hash(protocol),
            ),
            canonical_hash(protocol),
        )

    def record_assessment(
        self,
        assessment: PaperBurnInAssessment,
        snapshots: tuple[PaperOperatorSnapshot, ...],
    ) -> bool:
        protocol = self.repository.connection.execute(
            """SELECT session_id, definition_hash, payload_json, payload_hash
               FROM paper_burn_in_protocols WHERE protocol_id = ?""",
            (assessment.protocol_id,),
        ).fetchone()
        if (
            protocol is None
            or str(protocol[0]) != assessment.session_id
            or str(protocol[1]) != assessment.protocol_definition_hash
            or canonical_hash(json.loads(str(protocol[2]))) != str(protocol[3])
        ):
            raise ValueError("Phase 9B protocol dependency is missing or corrupt")
        ordered = tuple(sorted(snapshots, key=lambda item: (item.observed_at, item.snapshot_id)))
        if canonical_hash(tuple(canonical_hash(item) for item in ordered)) != (
            assessment.snapshot_root_hash
        ):
            raise ValueError("Phase 9B snapshot root mismatch")
        for snapshot in ordered:
            row = self.repository.connection.execute(
                """SELECT payload_json, payload_hash FROM paper_operator_snapshots
                   WHERE snapshot_id = ? AND session_id = ?""",
                (snapshot.snapshot_id, assessment.session_id),
            ).fetchone()
            if row is None or canonical_hash(json.loads(str(row[0]))) != str(row[1]):
                raise ValueError("Phase 9B snapshot dependency is missing or corrupt")
        return self._insert(
            "paper_burn_in_assessments",
            "assessment_id",
            assessment.assessment_id,
            """INSERT OR IGNORE INTO paper_burn_in_assessments
               (assessment_id, protocol_id, session_id, evaluated_at, state,
                snapshot_root_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                assessment.assessment_id,
                assessment.protocol_id,
                assessment.session_id,
                _time(assessment.evaluated_at),
                assessment.state.value,
                assessment.snapshot_root_hash,
                canonical_json(assessment),
                canonical_hash(assessment),
            ),
            canonical_hash(assessment),
        )

    def _insert(
        self,
        table: str,
        identity_column: str,
        identity: str,
        statement: str,
        values: tuple[object, ...],
        payload_hash: str,
    ) -> bool:
        cursor = self.repository.connection.execute(statement, values)
        if not cursor.rowcount:
            row = self.repository.connection.execute(
                f"SELECT payload_json, payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if row is None or canonical_hash(json.loads(str(row[0]))) != str(row[1]) or (
                str(row[1]) != payload_hash
            ):
                raise ValueError(f"conflicting Phase 9B record: {identity}")
            return False
        self.repository.connection.commit()
        return True


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("Phase 9B timestamp must be UTC")
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
