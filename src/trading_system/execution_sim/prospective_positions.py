"""Offline append-only one-share position claims and terminal stop receipts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from trading_system.domain import Candle, Direction, Timeframe
from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.execution_sim.prospective_stop import StopAssessment, assess_stop
from trading_system.market_data.calendar import SessionCalendar
from trading_system.persistence import SQLiteRepository
from trading_system.risk import PositionState
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


def _stored_integrity(payload: str, digest: str) -> None:
    if canonical_hash(json.loads(payload)) != digest:
        raise ValueError("stored shadow receipt integrity failure")


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _next_slot(
    calendar: SessionCalendar, timeframe: Timeframe, previous_close: datetime,
) -> tuple[datetime, datetime]:
    step = timedelta(hours=1 if timeframe is Timeframe.HOUR_1 else 4)
    for offset in range(15):
        day = previous_close.date() + timedelta(days=offset)
        bounds = calendar.bounds(day)
        if bounds is None:
            continue
        start, end = bounds
        if previous_close <= start:
            return start, min(start + step, end)
        if start < previous_close < end:
            return previous_close, min(previous_close + step, end)
    raise ValueError("next XNYS bar unavailable in calendar")


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

    def process_bar(
        self, trade_id: str, *, calendar: SessionCalendar, candle: Candle, atr20: Decimal,
        feature_known_at: datetime, received_at: datetime, as_of: datetime,
    ) -> StopAssessment:
        row = self.connection.execute(
            "SELECT symbol, entry_price, initial_stop, known_at, payload_json, payload_hash "
            "FROM prospective_shadow_positions WHERE trade_id = ?", (trade_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown shadow trade")
        symbol, entry_text, stop_text, known_text, payload, digest = row
        _stored_integrity(payload, digest)
        data = json.loads(payload)
        request, assessment = data
        stored_calendar = self.connection.execute(
            "SELECT json_extract(payload_json, '$[1]'), "
            "json_extract(payload_json, '$[2]') FROM prospective_entry_requests "
            "WHERE decision_id = ?", (request["decision_id"],),
        ).fetchone()
        if stored_calendar is None or (calendar.name, calendar.version) != stored_calendar:
            raise ValueError("entry calendar provenance mismatch")
        if calendar.name != "XNYS":
            raise ValueError("XNYS calendar required")
        timeframe = Timeframe(request["plan"]["timeframe"])
        if candle.symbol != symbol or candle.timeframe is not timeframe:
            raise ValueError("shadow bar identity mismatch")
        last = self.connection.execute(
            "SELECT ordinal, open_time, close_time, known_at, payload_json, payload_hash, "
            "candle_id FROM prospective_shadow_bar_receipts WHERE trade_id = ? "
            "ORDER BY ordinal DESC LIMIT 1", (trade_id,),
        ).fetchone()
        duplicate = last is not None and last[6] == candle.candle_id
        if last is not None:
            _stored_integrity(last[4], last[5])
            if _time(last[3]) > as_of:
                raise ValueError("bar receipt unavailable at cutoff")
            if json.loads(last[4])[0]["source_revision"] != candle.source_revision:
                raise ValueError("shadow source revision changed")
        if duplicate:
            previous = self.connection.execute(
                "SELECT known_at FROM prospective_shadow_bar_receipts "
                "WHERE trade_id = ? AND ordinal = ?", (trade_id, last[0] - 1),
            ).fetchone()
            state_known_at = _time(previous[0]) if previous else _time(known_text)
            ordinal = int(last[0])
            expected = (_time(last[1]), _time(last[2]))
        else:
            if self.connection.execute(
                "SELECT 1 FROM prospective_shadow_exit_receipts WHERE trade_id = ?", (trade_id,),
            ).fetchone():
                raise ValueError("shadow trade already closed; terminal receipt is immutable")
            if last is None:
                entry_open = _time(assessment["event_time"]["__datetime__"])
                bounds = calendar.bounds(entry_open.date())
                if bounds is None or not bounds[0] <= entry_open < bounds[1]:
                    raise ValueError("entry slot unavailable in calendar")
                step = timedelta(hours=1 if timeframe is Timeframe.HOUR_1 else 4)
                previous_close = min(entry_open + step, bounds[1])
                state_known_at = _time(known_text)
                ordinal = 1
            else:
                previous_close = _time(last[2])
                state_known_at = _time(last[3])
                ordinal = int(last[0]) + 1
            expected = _next_slot(calendar, timeframe, previous_close)
        if (
            (candle.open_time, candle.close_time) != expected
            or candle.session_date != expected[0].date()
        ):
            raise ValueError("expected exact next XNYS bar; missing or shifted bar")
        entry, stop = Decimal(entry_text), Decimal(stop_text)
        state = PositionState(Direction.LONG, entry, stop, stop, entry - stop, entry)
        adjustment = Decimal(request["adjustment_factor"]["__decimal__"])
        result = assess_stop(
            trade_id=trade_id, symbol=symbol, state=state,
            state_known_at=state_known_at, atr20=atr20,
            feature_known_at=feature_known_at, adjustment_factor=adjustment,
            candle=candle, received_at=received_at, as_of=as_of,
        )
        bar_payload = canonical_json((candle, atr20, feature_known_at, received_at, result))
        if duplicate:
            if (last[4], last[5]) != (bar_payload, canonical_hash(json.loads(bar_payload))):
                raise ValueError("shadow bar receipt cannot be revised")
            return result
        self.connection.execute("SAVEPOINT prospective_shadow_bar")
        try:
            self.connection.execute(
                "INSERT INTO prospective_shadow_bar_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trade_id, ordinal, candle.candle_id, candle.open_time.isoformat(),
                    candle.close_time.isoformat(), result.known_at.isoformat(),
                    bar_payload, canonical_hash(json.loads(bar_payload)),
                ),
            )
            if result.status == "STOP_EXIT_MODELLED":
                self.connection.execute(
                    "INSERT INTO prospective_shadow_exit_receipts VALUES (?, ?, ?, ?)",
                    (trade_id, result.known_at.isoformat(), canonical_json(result),
                     canonical_hash(result)),
                )
            self.connection.execute("RELEASE prospective_shadow_bar")
        except Exception:
            self.connection.execute("ROLLBACK TO prospective_shadow_bar")
            self.connection.execute("RELEASE prospective_shadow_bar")
            raise
        return result
