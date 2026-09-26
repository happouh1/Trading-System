"""Append-only offline prospective control receipts."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.execution_sim.prospective_controls import (
    ProspectiveControlAssessment,
    ProspectiveControlsConfig,
    assess_prospective_controls,
)
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import PortfolioCandidate, PortfolioConfig, PortfolioState
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveControlRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def assess(
        self, *, entry: ProspectiveEntry, entry_assessment: EntryAssessment,
        portfolio_state: PortfolioState, candidate: PortfolioCandidate,
        portfolio_config: PortfolioConfig, controls_config: ProspectiveControlsConfig,
        as_of: datetime,
    ) -> ProspectiveControlAssessment:
        result = assess_prospective_controls(
            entry=entry, entry_assessment=entry_assessment,
            portfolio_state=portfolio_state, candidate=candidate,
            portfolio_config=portfolio_config, controls_config=controls_config,
        )
        if result.known_at > as_of:
            raise ValueError("prospective control receipt unavailable at cutoff")
        payload, digest = canonical_json(result), canonical_hash(result)
        connection = self.repository.connection
        connection.execute("SAVEPOINT prospective_control")
        try:
            prior = connection.execute(
                "SELECT known_at, payload_json, payload_hash "
                "FROM prospective_control_assessments WHERE decision_id = ?",
                (entry.decision_id,),
            ).fetchone()
            if prior is not None:
                if datetime.fromisoformat(prior[0]) > as_of:
                    raise ValueError("stored prospective control unavailable at cutoff")
                if canonical_hash(json.loads(prior[1])) != prior[2]:
                    raise ValueError("stored prospective control integrity failure")
                if prior != (result.known_at.isoformat(), payload, digest):
                    raise ValueError("prospective control assessment cannot be revised")
            else:
                connection.execute(
                    "INSERT INTO prospective_control_assessments VALUES (?, ?, ?, ?, ?)",
                    (entry.decision_id, result.known_at.isoformat(), result.status,
                     payload, digest),
                )
            connection.execute("RELEASE prospective_control")
            return result
        except Exception:
            connection.execute("ROLLBACK TO prospective_control")
            connection.execute("RELEASE prospective_control")
            raise
