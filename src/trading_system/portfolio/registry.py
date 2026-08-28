"""Append-only Phase 4A portfolio persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.persistence import SQLiteRepository
from trading_system.portfolio.contracts import PortfolioAssessment, PortfolioState
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class PortfolioRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def insert_state(self, state: PortfolioState, config_hash: str) -> bool:
        payload_json = canonical_json(state)
        payload_hash = canonical_hash(state)
        identity = (state.portfolio_id, _time(state.as_of))
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO portfolio_states
               (portfolio_id, as_of, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (*identity, config_hash, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT config_hash, payload_hash FROM portfolio_states
                   WHERE portfolio_id = ? AND as_of = ?""",
                identity,
            ).fetchone()
            if stored != (config_hash, payload_hash):
                raise ValueError("conflicting portfolio state payload")
            return False
        self.repository.connection.commit()
        return True

    def insert_assessment(self, assessment: PortfolioAssessment) -> bool:
        payload_json = assessment.to_json()
        payload_hash = canonical_hash(assessment)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO portfolio_assessments
               (assessment_id, portfolio_id, candidate_id, known_at, strategy_class,
                action, reason_codes_json, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                assessment.assessment_id,
                assessment.portfolio_id,
                assessment.candidate_id,
                _time(assessment.known_at),
                assessment.strategy_class.value,
                assessment.action.value,
                canonical_json(assessment.reason_codes),
                assessment.config_hash,
                payload_json,
                payload_hash,
            ),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                "SELECT payload_hash FROM portfolio_assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError("conflicting portfolio assessment payload")
            return False
        self.repository.connection.commit()
        return True

    def assessment_payloads(self, portfolio_id: str) -> tuple[str, ...]:
        rows = self.repository.connection.execute(
            """SELECT payload_json FROM portfolio_assessments
               WHERE portfolio_id = ? ORDER BY known_at, assessment_id""",
            (portfolio_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)
