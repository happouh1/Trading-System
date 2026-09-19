"""Offline append-only one-share position claims and terminal stop receipts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from trading_system.domain import Candle, Direction
from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.execution_sim.prospective_stop import StopAssessment, assess_stop
from trading_system.persistence import SQLiteRepository
from trading_system.risk import PositionState
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


def _stored_integrity(payload: str, digest: str) -> None:
    if canonical_hash(json.loads(payload)) != digest:
        raise ValueError("stored shadow receipt integrity failure")


class OfflineShadowPositions:
    """A separate offline registry; no paper or broker routing uses it."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.connection = repository.connection

    def open(self, request: ProspectiveEntry, assessment: EntryAssessment) -> str:
        if (
            assessment.decision_id != request.decision_id or assessment.status != "ENTRY_MODELLED"
            or assessment.fill_price is None or assessment.quantity != 1
            or assessment.known_at < request.recorded_at
            or assessment.fill_price <= request.plan.initial_stop
        ):
            raise ValueError("a modelled, causal one-share entry is required")
        row = self.connection.execute(
            "SELECT request_hash, payload_json FROM prospective_entry_requests "
            "WHERE decision_id = ?",
            (request.decision_id,),
        ).fetchone()
        if row is None or canonical_hash(json.loads(row[1])) != row[0]:
            raise ValueError("entry request is unavailable or corrupt")
        expected_request = json.loads(canonical_json(request))
        if json.loads(row[1])[0] != expected_request:
            raise ValueError("entry request does not match the stored decision")
        outcome = self.connection.execute(
            "SELECT payload_hash, payload_json FROM prospective_entry_outcomes "
            "WHERE decision_id = ?",
            (request.decision_id,),
        ).fetchone()
        if outcome is None or outcome != (canonical_hash(assessment), canonical_json(assessment)):
            raise ValueError("modelled entry must match an immutable terminal receipt")
        trade_id = deterministic_id("prospective_shadow_trade", assessment.assessment_id)
        values = (
            trade_id, request.decision_id, request.plan.symbol,
            format(assessment.fill_price, "f"), format(request.plan.initial_stop, "f"),
            assessment.known_at.isoformat(), canonical_json((request, assessment)),
            canonical_hash((request, assessment)),
        )
        prior = self.connection.execute(
            "SELECT trade_id, decision_id, symbol, entry_price, initial_stop, known_at, "
            "payload_json, payload_hash FROM prospective_shadow_positions WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
        if prior is not None:
            if prior != values:
                raise ValueError("shadow trade identity conflict")
            return trade_id
        last_exit = self.connection.execute(
            "SELECT MAX(x.known_at) FROM prospective_shadow_positions p "
            "JOIN prospective_shadow_exit_receipts x ON x.trade_id = p.trade_id "
            "WHERE p.symbol = ?", (request.plan.symbol,),
        ).fetchone()[0]
        if last_exit is not None and (
            datetime.fromisoformat(last_exit) > request.recorded_at
            or datetime.fromisoformat(last_exit) > assessment.event_time
        ):
            raise ValueError("prior shadow exit unavailable at new entry")
        self.connection.execute("SAVEPOINT prospective_shadow_open")
        try:
            self.connection.execute(
                "INSERT INTO prospective_shadow_positions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values,
            )
            self.connection.execute("RELEASE prospective_shadow_open")
        except sqlite3.IntegrityError as exc:
            self.connection.execute("ROLLBACK TO prospective_shadow_open")
            self.connection.execute("RELEASE prospective_shadow_open")
            raise ValueError("symbol already has an open shadow position") from exc
        return trade_id

    def close_stop(
        self, trade_id: str, *, candle: Candle, atr20: Decimal,
        feature_known_at: datetime, received_at: datetime, as_of: datetime,
    ) -> StopAssessment | None:
        row = self.connection.execute(
            "SELECT symbol, entry_price, initial_stop, known_at, payload_json, payload_hash "
            "FROM prospective_shadow_positions WHERE trade_id = ?", (trade_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown shadow trade")
        symbol, entry_text, stop_text, known_text, payload, digest = row
        _stored_integrity(payload, digest)
        prior = self.connection.execute(
            "SELECT known_at, payload_json, payload_hash FROM prospective_shadow_exit_receipts "
            "WHERE trade_id = ?", (trade_id,),
        ).fetchone()
        if prior is not None:
            if datetime.fromisoformat(prior[0]) > as_of:
                raise ValueError("exit receipt unavailable at cutoff")
            _stored_integrity(prior[1], prior[2])
            raise ValueError("shadow trade already closed; terminal receipt is immutable")
        entry, stop = Decimal(entry_text), Decimal(stop_text)
        state = PositionState(Direction.LONG, entry, stop, stop, entry - stop, entry)
        request = payload
        data = json.loads(request)
        adjustment = Decimal(data[0]["adjustment_factor"]["__decimal__"])
        result = assess_stop(
            trade_id=trade_id, symbol=symbol, state=state,
            state_known_at=datetime.fromisoformat(known_text), atr20=atr20,
            feature_known_at=feature_known_at, adjustment_factor=adjustment,
            candle=candle, received_at=received_at, as_of=as_of,
        )
        if result.status != "STOP_EXIT_MODELLED":
            return None
        self.connection.execute("SAVEPOINT prospective_shadow_close")
        try:
            self.connection.execute(
                "INSERT INTO prospective_shadow_exit_receipts VALUES (?, ?, ?, ?)",
                (
                    trade_id, result.known_at.isoformat(), canonical_json(result),
                    canonical_hash(result),
                ),
            )
            self.connection.execute("RELEASE prospective_shadow_close")
        except Exception:
            self.connection.execute("ROLLBACK TO prospective_shadow_close")
            self.connection.execute("RELEASE prospective_shadow_close")
            raise
        return result
