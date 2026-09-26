"""Offline append-only one-share position, bar, and exit receipts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from trading_system.domain import Candle, Direction, Timeframe
from trading_system.execution_sim.prospective import EntryAssessment, ProspectiveEntry
from trading_system.execution_sim.prospective_controls import ProspectiveControlAssessment
from trading_system.execution_sim.prospective_max_hold import (
    MAX_HOLD_BARS,
    MaxHoldAssessment,
    assess_max_hold,
)
from trading_system.execution_sim.prospective_max_hold import VERSION as MAX_HOLD_VERSION
from trading_system.execution_sim.prospective_opposing_trap import (
    VERSION as TRAP_VERSION,
)
from trading_system.execution_sim.prospective_opposing_trap import (
    OpposingTrapEvidence,
    OpposingTrapExitAssessment,
    assess_opposing_trap_exit,
    validate_opposing_trap_signal,
)
from trading_system.execution_sim.prospective_stop import StopAssessment, assess_stop
from trading_system.execution_sim.prospective_structural_exit import (
    VERSION as STRUCTURAL_VERSION,
)
from trading_system.execution_sim.prospective_structural_exit import (
    StructuralExitAssessment,
    assess_structural_exit,
)
from trading_system.execution_sim.prospective_trail import (
    TrailAssessment,
    TrailEvidence,
    assess_trail,
)
from trading_system.market_data.calendar import SessionCalendar
from trading_system.persistence import SQLiteRepository
from trading_system.risk import PositionState
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


def _stored_integrity(payload: str, digest: str) -> None:
    if canonical_hash(json.loads(payload)) != digest:
        raise ValueError("stored shadow receipt integrity failure")


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _trail_state(payload: str) -> PositionState:
    data = json.loads(payload)["next_state"]
    if not isinstance(data["exit_queued"], bool):
        raise ValueError("invalid stored trail queue flag")
    return PositionState(
        direction=Direction(data["direction"]),
        entry=Decimal(data["entry"]["__decimal__"]),
        initial_stop=Decimal(data["initial_stop"]["__decimal__"]),
        current_stop=Decimal(data["current_stop"]["__decimal__"]),
        risk=Decimal(data["risk"]["__decimal__"]),
        favorable_extreme=Decimal(data["favorable_extreme"]["__decimal__"]),
        bars_held=int(data["bars_held"]),
        exit_queued=data["exit_queued"],
    )


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

    def open_controlled(
        self, request: ProspectiveEntry, assessment: EntryAssessment,
        controls: ProspectiveControlAssessment,
    ) -> str:
        if (
            controls.decision_id != request.decision_id
            or controls.known_at != assessment.known_at
            or controls.status != "CONTROL_APPROVED"
            or controls.reason_codes
            or controls.portfolio_assessment.candidate_id != request.decision_id
            or controls.portfolio_assessment.action.value != "ACCEPT"
            or controls.fee_per_share_per_side != 0
            or controls.estimated_round_trip_fees != 0
            or controls.fees_status != "SPEC_DEFAULT_ZERO_DECLARED"
            or controls.spread_status != "COMBINED_IN_DECLARED_SLIPPAGE"
            or controls.qualifying_completed_trade or controls.broker_write_performed
            or controls.cohort_activated
        ):
            raise ValueError("approved offline prospective controls are required")
        stored = self.connection.execute(
            "SELECT known_at, status, payload_json, payload_hash "
            "FROM prospective_control_assessments WHERE decision_id = ?",
            (request.decision_id,),
        ).fetchone()
        expected = (
            controls.known_at.isoformat(), controls.status,
            canonical_json(controls), canonical_hash(controls),
        )
        if stored != expected:
            raise ValueError("prospective control receipt is unavailable or does not match")
        return self.open(request, assessment)

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
        trail_evidence: TrailEvidence | None = None,
        opposing_trap: OpposingTrapEvidence | None = None,
    ) -> StopAssessment | MaxHoldAssessment | StructuralExitAssessment | OpposingTrapExitAssessment:
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
        if _time(known_text) != _time(assessment["known_at"]["__datetime__"]):
            raise ValueError("entry receipt knowledge time mismatch")
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
        queued = self.connection.execute(
            "SELECT reason, signal_ordinal, signal_candle_id, known_at, payload_json, "
            "payload_hash FROM prospective_shadow_queued_exits WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
        structural_queue = self.connection.execute(
            "SELECT signal_ordinal, signal_candle_id, known_at, payload_json, payload_hash "
            "FROM prospective_shadow_structural_queues WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
        trap_queue = self.connection.execute(
            "SELECT signal_ordinal, signal_candle_id, signal_event_id, confidence, "
            "known_at, payload_json, payload_hash "
            "FROM prospective_shadow_trap_queues WHERE trade_id = ?", (trade_id,),
        ).fetchone()
        if sum(item is not None for item in (queued, structural_queue, trap_queue)) > 1:
            raise ValueError("conflicting shadow exit queues")
        if queued is not None:
            _stored_integrity(queued[4], queued[5])
            if (
                queued[0] != "MAX_HOLD" or queued[1] != MAX_HOLD_BARS
                or queued[4] != canonical_json((
                    MAX_HOLD_VERSION, MAX_HOLD_BARS, trade_id, queued[2],
                    _time(queued[3]),
                ))
            ):
                raise ValueError("queued maximum-hold receipt mismatch")
            if _time(queued[3]) > as_of:
                raise ValueError("queued exit unavailable at cutoff")
        if structural_queue is not None:
            _stored_integrity(structural_queue[3], structural_queue[4])
            if (
                not 1 <= structural_queue[0] <= MAX_HOLD_BARS
                or structural_queue[3] != canonical_json((
                    STRUCTURAL_VERSION, trade_id, structural_queue[0],
                    structural_queue[1], _time(structural_queue[2]),
                ))
            ):
                raise ValueError("queued structural receipt mismatch")
            if _time(structural_queue[2]) > as_of:
                raise ValueError("queued exit unavailable at cutoff")
        if trap_queue is not None:
            _stored_integrity(trap_queue[5], trap_queue[6])
            confidence = Decimal(trap_queue[3])
            if (
                not 1 <= trap_queue[0] <= MAX_HOLD_BARS
                or not confidence.is_finite() or not Decimal(75) <= confidence <= 100
                or trap_queue[5] != canonical_json((
                    TRAP_VERSION, trade_id, trap_queue[0], trap_queue[1],
                    trap_queue[2], confidence, _time(trap_queue[4]),
                ))
            ):
                raise ValueError("queued opposing-trap receipt mismatch")
            if _time(trap_queue[4]) > as_of:
                raise ValueError("queued exit unavailable at cutoff")
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
            state_known_at = (
                _time(previous[0]) if previous
                else _time(request["recorded_at"]["__datetime__"])
            )
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
                expected = (entry_open, min(entry_open + step, bounds[1]))
                state_known_at = _time(request["recorded_at"]["__datetime__"])
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
        if ordinal == 1 and (
            candle.candle_id != assessment["source_candle_id"]
            or atr20 != Decimal(request["atr20"]["__decimal__"])
            or feature_known_at != _time(request["feature_known_at"]["__datetime__"])
            or received_at != _time(assessment["known_at"]["__datetime__"])
        ):
            raise ValueError("entry bar receipt or prior features mismatch")
        queue_signal = (
            MAX_HOLD_BARS if queued is not None else
            int(structural_queue[0]) if structural_queue is not None else
            int(trap_queue[0]) if trap_queue is not None else None
        )
        queue_candle_id = (
            queued[2] if queued is not None else
            structural_queue[1] if structural_queue is not None else
            trap_queue[1] if trap_queue is not None else None
        )
        queue_known_at = (
            _time(queued[3]) if queued is not None else
            _time(structural_queue[2]) if structural_queue is not None else
            _time(trap_queue[4]) if trap_queue is not None else None
        )
        if (
            (queue_signal is None and ordinal > MAX_HOLD_BARS)
            or (queue_signal is not None and ordinal not in (
                queue_signal, queue_signal + 1,
            ))
            or (queue_signal == ordinal and (
                queue_candle_id, queue_known_at,
            ) != (candle.candle_id, received_at))
        ):
            raise ValueError("queued exit and bar sequence mismatch")
        queued_fill = queue_signal is not None and ordinal == queue_signal + 1
        if queued_fill and (trail_evidence is not None or opposing_trap is not None):
            raise ValueError("queued next-open exit cannot update exit signals")
        entry, stop = Decimal(entry_text), Decimal(stop_text)
        state = PositionState(Direction.LONG, entry, stop, stop, entry - stop, entry)
        first_trail = self.connection.execute(
            "SELECT 1 FROM prospective_shadow_trail_receipts "
            "WHERE trade_id = ? AND ordinal = 1", (trade_id,),
        ).fetchone()
        managed = first_trail is not None
        if not managed and self.connection.execute(
            "SELECT 1 FROM prospective_shadow_trail_receipts WHERE trade_id = ? LIMIT 1",
            (trade_id,),
        ).fetchone():
            raise ValueError("shadow trail mode lacks its entry-bar receipt")
        if ordinal > 1 and managed:
            prior_trail = self.connection.execute(
                "SELECT candle_id, known_at, payload_json, payload_hash "
                "FROM prospective_shadow_trail_receipts WHERE trade_id = ? AND ordinal = ?",
                (trade_id, ordinal - 1),
            ).fetchone()
            if prior_trail is None:
                raise ValueError("missing prior shadow trail receipt")
            _stored_integrity(prior_trail[2], prior_trail[3])
            prior_bar = self.connection.execute(
                "SELECT candle_id, known_at, payload_json, payload_hash "
                "FROM prospective_shadow_bar_receipts WHERE trade_id = ? AND ordinal = ?",
                (trade_id, ordinal - 1),
            ).fetchone()
            if prior_bar is None:
                raise ValueError("missing prior shadow bar receipt")
            _stored_integrity(prior_bar[2], prior_bar[3])
            prior_data = json.loads(prior_bar[2])
            if (
                (prior_trail[0], prior_trail[1]) != (prior_bar[0], prior_bar[1])
                or _time(prior_trail[1]) != state_known_at
                or len(prior_data) not in (7, 8)
                or canonical_json(prior_data[6]) != prior_trail[2]
            ):
                raise ValueError("prior trail knowledge time mismatch")
            state = _trail_state(prior_trail[2])
            if (
                state.direction is not Direction.LONG or state.entry != entry
                or state.initial_stop != stop or state.risk != entry - stop
                or state.bars_held != ordinal - 1
                or state.current_stop < stop or not state.current_stop.is_finite()
                or state.exit_queued != (
                    structural_queue is not None
                    and queue_signal == ordinal - 1
                )
            ):
                raise ValueError("invalid prior shadow trail state")
        adjustment = Decimal(request["adjustment_factor"]["__decimal__"])
        if queued_fill:
            signal = self.connection.execute(
                "SELECT candle_id, known_at, payload_json, payload_hash "
                "FROM prospective_shadow_bar_receipts WHERE trade_id = ? AND ordinal = ?",
                (trade_id, queue_signal),
            ).fetchone()
            if signal is None or (signal[0], _time(signal[1])) != (
                queue_candle_id, queue_known_at,
            ):
                raise ValueError("queued exit signal bar mismatch")
            _stored_integrity(signal[2], signal[3])
            if json.loads(signal[2])[4]["status"] != "STOP_NOT_HIT":
                raise ValueError("queued exit requires unhit signal bar")
            if queued is not None:
                result: (
                    StopAssessment | MaxHoldAssessment | StructuralExitAssessment
                    | OpposingTrapExitAssessment
                ) = (
                    assess_max_hold(
                        trade_id=trade_id, symbol=symbol, signal_candle_id=queued[2],
                        signal_known_at=_time(queued[3]), candle=candle, atr20=atr20,
                        feature_known_at=feature_known_at, adjustment_factor=adjustment,
                        received_at=received_at, as_of=as_of,
                    )
                )
            elif structural_queue is not None:
                if queue_candle_id is None or queue_known_at is None:
                    raise ValueError("structural queue signal unavailable")
                signal_trail = self.connection.execute(
                    "SELECT payload_json, payload_hash FROM prospective_shadow_trail_receipts "
                    "WHERE trade_id = ? AND ordinal = ?", (trade_id, queue_signal),
                ).fetchone()
                if signal_trail is None:
                    raise ValueError("structural signal trail receipt unavailable")
                _stored_integrity(signal_trail[0], signal_trail[1])
                trail_data = json.loads(signal_trail[0])
                if trail_data["status"] != "STRUCTURAL_DAMAGE_EXIT_QUEUED":
                    raise ValueError("structural signal trail status mismatch")
                result = assess_structural_exit(
                    trade_id=trade_id, symbol=symbol,
                    signal_candle_id=queue_candle_id,
                    signal_known_at=queue_known_at,
                    signal_damage_score=Decimal(trail_data["damage_score"]["__decimal__"]),
                    candle=candle, atr20=atr20,
                    feature_known_at=feature_known_at, adjustment_factor=adjustment,
                    received_at=received_at, as_of=as_of,
                )
            elif trap_queue is not None:
                if queue_candle_id is None or queue_known_at is None:
                    raise ValueError("opposing-trap queue signal unavailable")
                signal_data = json.loads(signal[2])
                if len(signal_data) != 8 or (
                    signal_data[7]["event"]["event_id"] != trap_queue[2]
                    or signal_data[7]["event"]["symbol"] != symbol
                    or signal_data[7]["event"]["timeframe"] != timeframe.value
                    or signal_data[7]["event"]["direction"] != Direction.SHORT.value
                    or signal_data[7]["event"]["new_state"] != "TRAP_CONFIRMED"
                    or queue_candle_id not in signal_data[7]["event"]["evidence_candle_ids"]
                    or signal_data[7]["confidence"] != json.loads(
                        canonical_json(Decimal(trap_queue[3]))
                    )
                    or not _time(signal_data[0]["close_time"]["__datetime__"])
                    <= _time(signal_data[7]["event"]["known_at"]["__datetime__"])
                    <= queue_known_at
                ):
                    raise ValueError("opposing-trap signal evidence mismatch")
                result = assess_opposing_trap_exit(
                    trade_id=trade_id, symbol=symbol,
                    signal_candle_id=queue_candle_id,
                    signal_event_id=trap_queue[2], signal_known_at=queue_known_at,
                    signal_confidence=Decimal(trap_queue[3]), candle=candle,
                    atr20=atr20, feature_known_at=feature_known_at,
                    adjustment_factor=adjustment, received_at=received_at, as_of=as_of,
                )
            else:
                raise ValueError("queued exit kind unavailable")
        else:
            result = assess_stop(
                trade_id=trade_id, symbol=symbol, state=state,
                state_known_at=state_known_at, atr20=atr20,
                feature_known_at=feature_known_at, adjustment_factor=adjustment,
                candle=candle, received_at=received_at, as_of=as_of,
            )
        trail_result: TrailAssessment | None = None
        if result.status == "STOP_NOT_HIT":
            if ordinal > 1 and (trail_evidence is not None) != managed:
                raise ValueError("shadow trail mode cannot change after the entry bar")
            if trail_evidence is not None:
                trail_result = assess_trail(
                    trade_id=trade_id, symbol=symbol, prior_state=state,
                    prior_state_known_at=state_known_at, candle=candle,
                    evidence=trail_evidence, adjustment_factor=adjustment,
                    received_at=received_at, as_of=as_of,
                )
            if opposing_trap is not None:
                validate_opposing_trap_signal(
                    evidence=opposing_trap, candle=candle, received_at=received_at,
                )
        bar_payload = canonical_json(
            (candle, atr20, feature_known_at, received_at, result)
            if trail_result is None and opposing_trap is None else
            (candle, atr20, feature_known_at, received_at, result,
             trail_evidence, trail_result)
            if opposing_trap is None else
            (candle, atr20, feature_known_at, received_at, result,
             trail_evidence, trail_result, opposing_trap)
        )
        if duplicate:
            if (last[4], last[5]) != (bar_payload, canonical_hash(json.loads(bar_payload))):
                raise ValueError("shadow bar receipt cannot be revised")
            if trail_result is not None:
                saved_trail = self.connection.execute(
                    "SELECT candle_id, known_at, payload_json, payload_hash "
                    "FROM prospective_shadow_trail_receipts WHERE trade_id = ? AND ordinal = ?",
                    (trade_id, ordinal),
                ).fetchone()
                if saved_trail != (
                    candle.candle_id, trail_result.known_at.isoformat(),
                    canonical_json(trail_result), canonical_hash(trail_result),
                ):
                    raise ValueError("shadow trail receipt cannot be revised")
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
            if trail_result is not None:
                self.connection.execute(
                    "INSERT INTO prospective_shadow_trail_receipts VALUES (?, ?, ?, ?, ?, ?)",
                    (trade_id, ordinal, candle.candle_id, trail_result.known_at.isoformat(),
                     canonical_json(trail_result), canonical_hash(trail_result)),
                )
            if result.status == "STOP_EXIT_MODELLED":
                self.connection.execute(
                    "INSERT INTO prospective_shadow_exit_receipts VALUES (?, ?, ?, ?)",
                    (trade_id, result.known_at.isoformat(), canonical_json(result),
                     canonical_hash(result)),
                )
            elif trail_result is not None and trail_result.next_state.exit_queued:
                queue_payload = (
                    STRUCTURAL_VERSION, trade_id, ordinal, candle.candle_id,
                    trail_result.known_at,
                )
                self.connection.execute(
                    "INSERT INTO prospective_shadow_structural_queues "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (trade_id, ordinal, candle.candle_id,
                     trail_result.known_at.isoformat(), canonical_json(queue_payload),
                     canonical_hash(queue_payload)),
                )
            elif result.status == "STOP_NOT_HIT" and opposing_trap is not None:
                trap_payload = (
                    TRAP_VERSION, trade_id, ordinal, candle.candle_id,
                    opposing_trap.event.event_id, opposing_trap.confidence, received_at,
                )
                self.connection.execute(
                    "INSERT INTO prospective_shadow_trap_queues "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (trade_id, ordinal, candle.candle_id, opposing_trap.event.event_id,
                     format(opposing_trap.confidence, "f"), received_at.isoformat(),
                     canonical_json(trap_payload), canonical_hash(trap_payload)),
                )
            elif result.status == "STOP_NOT_HIT" and ordinal == MAX_HOLD_BARS:
                max_queue_payload = (
                    MAX_HOLD_VERSION, MAX_HOLD_BARS, trade_id, candle.candle_id,
                    result.known_at,
                )
                self.connection.execute(
                    "INSERT INTO prospective_shadow_queued_exits VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (trade_id, "MAX_HOLD", ordinal, candle.candle_id,
                     result.known_at.isoformat(), canonical_json(max_queue_payload),
                     canonical_hash(max_queue_payload)),
                )
            elif result.status in {
                "MAX_HOLD_EXIT_MODELLED", "STRUCTURAL_DAMAGE_EXIT_MODELLED",
                "OPPOSING_TRAP_EXIT_MODELLED",
            }:
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
