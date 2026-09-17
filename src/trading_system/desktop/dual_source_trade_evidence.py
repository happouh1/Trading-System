"""Unqualified, source-labelled candidate trade evidence for a future burn-in.

This module records provenance only. It never verifies fills, qualifies a trade,
changes a prospective assessment, or enables any execution path.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

TradeEvidenceSource = Literal["WEBULL_SANDBOX", "SHADOW_SIMULATED"]
_SOURCES = frozenset({"WEBULL_SANDBOX", "SHADOW_SIMULATED"})


def _utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


def _sha(value: str | None) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _time(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class TradeEvidenceCandidate:
    """Immutable metadata about a putative completed trade, not proof of one."""

    plan_id: str
    session_id: str
    decision_id: str
    source: TradeEvidenceSource
    source_trade_id: str
    entry_known_at: datetime
    exit_known_at: datetime
    recorded_at: datetime
    source_record_hash: str
    config_hash: str
    code_version: str
    simulation_model_hash: str | None = None
    schema_version: str = "DUAL_SOURCE_TRADE_CANDIDATE.1.0"

    def __post_init__(self) -> None:
        if (
            not all((self.plan_id, self.session_id, self.decision_id, self.source_trade_id,
                     self.code_version))
            or self.source not in _SOURCES
            or not all(_utc(value) for value in (
                self.entry_known_at, self.exit_known_at, self.recorded_at,
            ))
            or not self.entry_known_at < self.exit_known_at <= self.recorded_at
            or not _sha(self.source_record_hash)
            or not _sha(self.config_hash)
            or (self.source == "SHADOW_SIMULATED") != _sha(self.simulation_model_hash)
            or (self.source == "WEBULL_SANDBOX" and self.simulation_model_hash is not None)
            or self.schema_version != "DUAL_SOURCE_TRADE_CANDIDATE.1.0"
        ):
            raise ValueError("invalid unqualified dual-source trade candidate")

    @property
    def candidate_id(self) -> str:
        return deterministic_id("burn_in_trade_candidate", (
            self.plan_id, self.session_id, self.source, self.source_trade_id,
        ))


@dataclass(frozen=True, slots=True)
class CandidateSourceCounts:
    """Inspection counts only; these are never qualifying completed-trade counts."""

    plan_id: str
    as_of: datetime
    webull_sandbox_candidates: int
    shadow_simulated_candidates: int
    required_webull_sandbox_trades: int = 10
    required_shadow_simulated_trades: int = 10
    qualification_performed: bool = False

    def __post_init__(self) -> None:
        if (
            not self.plan_id
            or not _utc(self.as_of)
            or min(self.webull_sandbox_candidates, self.shadow_simulated_candidates) < 0
            or self.required_webull_sandbox_trades != 10
            or self.required_shadow_simulated_trades != 10
            or self.qualification_performed
        ):
            raise ValueError("invalid unqualified candidate counts")


class TradeEvidenceCandidateRegistry:
    """Append-only local SQLite registry that cannot emit a burn-in PASS."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def get(self, candidate_id: str) -> TradeEvidenceCandidate:
        row = self.repository.connection.execute(
            """SELECT plan_id, session_id, decision_id, source, source_trade_id,
                      entry_known_at, exit_known_at, recorded_at, source_record_hash,
                      config_hash, code_version, simulation_model_hash, schema_version,
                      payload_json, payload_hash
               FROM burn_in_trade_evidence_candidates WHERE candidate_id = ?""",
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise ValueError("trade candidate not found")
        candidate = TradeEvidenceCandidate(
            row[0], row[1], row[2], row[3], row[4],
            datetime.fromisoformat(row[5]), datetime.fromisoformat(row[6]),
            datetime.fromisoformat(row[7]), row[8], row[9], row[10], row[11], row[12],
        )
        if (
            candidate.candidate_id != candidate_id
            or canonical_hash(candidate) != row[14]
            or canonical_hash(json.loads(row[13])) != row[14]
        ):
            raise ValueError("stored trade candidate is inconsistent")
        return candidate

    def insert(self, candidate: TradeEvidenceCandidate) -> bool:
        connection = self.repository.connection
        session = connection.execute(
            "SELECT created_at, mode FROM paper_sessions WHERE session_id = ?",
            (candidate.session_id,),
        ).fetchone()
        if (
            session is None
            or str(session[1]) not in {"SHADOW", "SIMULATED"}
            or str(session[0]) > _time(candidate.entry_known_at)
        ):
            raise ValueError("candidate requires an existing causal shadow paper session")
        payload_json = canonical_json(candidate)
        payload_hash = canonical_hash(candidate)
        values = (
            candidate.candidate_id,
            candidate.plan_id,
            candidate.session_id,
            candidate.decision_id,
            candidate.source,
            candidate.source_trade_id,
            _time(candidate.entry_known_at),
            _time(candidate.exit_known_at),
            _time(candidate.recorded_at),
            candidate.source_record_hash,
            candidate.config_hash,
            candidate.code_version,
            candidate.simulation_model_hash,
            candidate.schema_version,
            payload_json,
            payload_hash,
        )
        try:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO burn_in_trade_evidence_candidates
                   (candidate_id, plan_id, session_id, decision_id, source, source_trade_id,
                    entry_known_at, exit_known_at, recorded_at, source_record_hash,
                    config_hash, code_version, simulation_model_hash, schema_version,
                    payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("invalid candidate persistence reference") from exc
        if cursor.rowcount == 0:
            stored = connection.execute(
                """SELECT candidate_id, payload_hash FROM burn_in_trade_evidence_candidates
                   WHERE plan_id = ? AND source = ? AND source_trade_id = ?""",
                (candidate.plan_id, candidate.source, candidate.source_trade_id),
            ).fetchone()
            if stored != (candidate.candidate_id, payload_hash):
                raise ValueError("conflicting dual-source trade candidate")
            return False
        connection.commit()
        return True

    def candidate_counts(self, plan_id: str, *, as_of: datetime) -> CandidateSourceCounts:
        if not plan_id or not _utc(as_of):
            raise ValueError("candidate inspection requires a plan ID and UTC cutoff")
        rows = self.repository.connection.execute(
            """SELECT source, COUNT(*) FROM burn_in_trade_evidence_candidates
               WHERE plan_id = ? AND recorded_at <= ? GROUP BY source ORDER BY source""",
            (plan_id, _time(as_of)),
        ).fetchall()
        counts = {str(source): int(count) for source, count in rows}
        return CandidateSourceCounts(
            plan_id,
            as_of,
            counts.get("WEBULL_SANDBOX", 0),
            counts.get("SHADOW_SIMULATED", 0),
        )
