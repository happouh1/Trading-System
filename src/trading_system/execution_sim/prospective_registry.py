"""Append-only offline entry receipts. First terminal assessment is final."""

from __future__ import annotations

import json
from datetime import datetime

from trading_system.domain import Candle
from trading_system.execution_sim.prospective import ProspectiveEntry, assess_entry
from trading_system.market_data.calendar import SessionCalendar
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


class ProspectiveEntryRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def assess(
        self, entry: ProspectiveEntry, *, calendar: SessionCalendar, as_of: datetime,
        candle: Candle | None = None, received_at: datetime | None = None,
    ) -> str:
        # Validate time and candidate input even when a terminal receipt already exists.
        result = assess_entry(entry, calendar=calendar, as_of=as_of,
                              candle=candle, received_at=received_at)
        request = (entry, calendar.name, calendar.version)
        request_json, request_hash = canonical_json(request), canonical_hash(request)
        connection = self.repository.connection
        connection.execute("SAVEPOINT prospective_entry")
        try:
            prior = connection.execute(
                "SELECT request_hash, payload_json FROM prospective_entry_requests "
                "WHERE decision_id = ?", (entry.decision_id,),
            ).fetchone()
            if prior is not None and prior != (request_hash, request_json):
                raise ValueError("decision identity reused with changed request")
            connection.execute(
                "INSERT OR IGNORE INTO prospective_entry_requests VALUES (?, ?, ?)",
                (entry.decision_id, request_hash, request_json),
            )
            terminal = connection.execute(
                "SELECT known_at, payload_hash, payload_json FROM prospective_entry_outcomes "
                "WHERE decision_id = ?", (entry.decision_id,),
            ).fetchone()
            if terminal is not None:
                if datetime.fromisoformat(terminal[0]) > as_of:
                    raise ValueError("terminal receipt unavailable at cutoff")
                if canonical_hash(json.loads(terminal[2])) != terminal[1]:
                    raise ValueError("terminal receipt integrity failure")
                if candle is not None and canonical_json(result) != terminal[2]:
                    raise ValueError("terminal assessment cannot be revised")
                payload = str(terminal[2])
            else:
                payload = canonical_json(result)
                if result.status != "WAITING":
                    connection.execute(
                        "INSERT INTO prospective_entry_outcomes VALUES (?, ?, ?, ?)",
                        (entry.decision_id, result.known_at.isoformat(),
                         canonical_hash(result), payload),
                    )
            connection.execute("RELEASE prospective_entry")
            return payload
        except Exception:
            connection.execute("ROLLBACK TO prospective_entry")
            connection.execute("RELEASE prospective_entry")
            raise
