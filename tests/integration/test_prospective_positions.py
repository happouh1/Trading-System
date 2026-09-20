from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_prospective_entry import CAL, OPEN, D, bar, entry
from tests.unit.test_prospective_opposing_trap import evidence as trap_evidence

from trading_system.domain import Candle, Timeframe
from trading_system.execution_sim.prospective import assess_entry
from trading_system.execution_sim.prospective_max_hold import MaxHoldAssessment
from trading_system.execution_sim.prospective_opposing_trap import OpposingTrapExitAssessment
from trading_system.execution_sim.prospective_positions import OfflineShadowPositions
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.execution_sim.prospective_structural_exit import StructuralExitAssessment
from trading_system.execution_sim.prospective_trail import TrailEvidence
from trading_system.market_data.calendar import StaticSessionCalendar
from trading_system.persistence import SQLiteRepository
from trading_system.risk import DamageInputs


def test_symbol_claim_survives_restart_and_releases_after_stop(tmp_path: Path) -> None:
    path = tmp_path / "positions.sqlite"
    candle = bar()
    at = candle.close_time
    first = entry()
    assessment = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        trade_id = OfflineShadowPositions(repo).open(first, assessment)
    with SQLiteRepository(path) as repo:
        repo.migrate()
        positions = OfflineShadowPositions(repo)
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_positions",
        ).fetchall() == [(trade_id,)]
        assert positions.open(first, assessment) == trade_id
        second = replace(first, decision_id="decision-2")
        second_assessment = assess_entry(
            second, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        ProspectiveEntryRegistry(repo).assess(
            second, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        with pytest.raises(ValueError, match="open shadow position"):
            positions.open(second, second_assessment)
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at,
        ).status == "STOP_NOT_HIT"
        stop_bar = replace(
            bar(), open_time=at, close_time=at + timedelta(hours=1),
            low=D(97), raw_low=D(97), candle_id="",
        )
        stopped = positions.process_bar(
            trade_id, calendar=CAL, candle=stop_bar, atr20=D(2), feature_known_at=OPEN,
            received_at=stop_bar.close_time, as_of=stop_bar.close_time,
        )
        assert stopped.status == "STOP_EXIT_MODELLED"
        assert stopped.fill_price == D("97.96")
        assert not stopped.qualifying_completed_trade
        with pytest.raises(ValueError, match="prior shadow exit unavailable"):
            positions.open(second, second_assessment)
        later = stop_bar.close_time
        third = replace(
            first, decision_id="decision-3", recorded_at=later, feature_known_at=later,
            plan=replace(first.plan, plan_id="p3", created_at=later),
        )
        next_bar = replace(
            bar(), open_time=later, close_time=later + timedelta(hours=1), candle_id="",
        )
        third_assessment = assess_entry(
            third, calendar=CAL, as_of=next_bar.close_time, candle=next_bar,
            received_at=next_bar.close_time,
        )
        ProspectiveEntryRegistry(repo).assess(
            third, calendar=CAL, as_of=next_bar.close_time, candle=next_bar,
            received_at=next_bar.close_time,
        )
        assert positions.open(third, third_assessment) != trade_id
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=stop_bar, atr20=D(2), feature_known_at=OPEN,
            received_at=stop_bar.close_time, as_of=stop_bar.close_time,
        ) == stopped
        with pytest.raises(ValueError, match="already closed"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=next_bar, atr20=D(2), feature_known_at=OPEN,
                received_at=next_bar.close_time, as_of=next_bar.close_time,
            )
        for table in (
            "prospective_shadow_positions", "prospective_shadow_bar_receipts",
            "prospective_shadow_exit_receipts",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                repo.connection.execute(f"DELETE FROM {table}")
    with SQLiteRepository(path) as repo:
        repo.migrate()
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == [(trade_id,)]


def test_bar_checks_are_contiguous_immutable_and_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "continuity.sqlite"
    first = entry()
    candle = bar()
    at = candle.close_time
    assessment = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    hold = replace(bar(), open_time=at, close_time=at + timedelta(hours=1), candle_id="")
    stop = replace(
        bar(), open_time=hold.close_time,
        close_time=hold.close_time + timedelta(hours=1),
        low=D(97), raw_low=D(97), candle_id="",
    )
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessment)
        with pytest.raises(ValueError, match="exact next XNYS bar"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=stop, atr20=D(2), feature_known_at=OPEN,
                received_at=stop.close_time, as_of=stop.close_time,
            )
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at,
        ).status == "STOP_NOT_HIT"
        with pytest.raises(ValueError, match="exact next XNYS bar"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=stop, atr20=D(2), feature_known_at=OPEN,
                received_at=stop.close_time, as_of=stop.close_time,
            )
        result = positions.process_bar(
            trade_id, calendar=CAL, candle=hold, atr20=D(2), feature_known_at=OPEN,
            received_at=hold.close_time, as_of=hold.close_time,
        )
        assert result.status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT ordinal, candle_id FROM prospective_shadow_bar_receipts",
        ).fetchall() == [(1, candle.candle_id), (2, hold.candle_id)]
    with SQLiteRepository(path) as repo:
        repo.migrate()
        positions = OfflineShadowPositions(repo)
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=hold, atr20=D(2), feature_known_at=OPEN,
            received_at=hold.close_time, as_of=hold.close_time,
        ) == result
        with pytest.raises(ValueError, match="cannot be revised"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=hold, atr20=D(3), feature_known_at=OPEN,
                received_at=hold.close_time, as_of=hold.close_time,
            )
        with pytest.raises(ValueError, match="source revision changed"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=replace(stop, source_revision="v2", candle_id=""),
                atr20=D(2), feature_known_at=OPEN,
                received_at=stop.close_time, as_of=stop.close_time,
            )
        with pytest.raises(ValueError, match="unavailable at cutoff"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=hold, atr20=D(2), feature_known_at=OPEN,
                received_at=hold.close_time, as_of=at,
            )
        stopped = positions.process_bar(
            trade_id, calendar=CAL, candle=stop, atr20=D(2), feature_known_at=OPEN,
            received_at=stop.close_time, as_of=stop.close_time,
        )
        assert stopped.status == "STOP_EXIT_MODELLED"
        assert repo.connection.execute(
            "SELECT ordinal FROM prospective_shadow_bar_receipts ORDER BY ordinal",
        ).fetchall() == [(1,), (2,), (3,)]


def test_partial_four_hour_session_requires_next_session_open(tmp_path: Path) -> None:
    next_open = OPEN + timedelta(days=1)
    calendar = StaticSessionCalendar({
        OPEN.date(): (OPEN, OPEN + timedelta(hours=6, minutes=30)),
        next_open.date(): (next_open, next_open + timedelta(hours=6, minutes=30)),
    })
    decision_time = OPEN + timedelta(hours=4)
    first = entry()
    first = replace(
        first, recorded_at=decision_time, feature_known_at=decision_time,
        plan=replace(first.plan, timeframe=Timeframe.HOUR_4, created_at=decision_time),
    )
    entry_bar = replace(
        bar(), timeframe=Timeframe.HOUR_4, open_time=decision_time,
        close_time=OPEN + timedelta(hours=6, minutes=30), candle_id="",
    )
    at = entry_bar.close_time
    assessment = assess_entry(
        first, calendar=calendar, as_of=at, candle=entry_bar, received_at=at,
    )
    next_bar = replace(
        entry_bar, open_time=next_open, close_time=next_open + timedelta(hours=4),
        session_date=next_open.date(), candle_id="",
    )
    with SQLiteRepository(tmp_path / "fourhour.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=calendar, as_of=at, candle=entry_bar, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessment)
        assert positions.process_bar(
            trade_id, calendar=calendar, candle=entry_bar, atr20=D(2),
            feature_known_at=decision_time, received_at=at, as_of=at,
        ).status == "STOP_NOT_HIT"
        result = positions.process_bar(
            trade_id, calendar=calendar, candle=next_bar, atr20=D(2),
            feature_known_at=decision_time, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        )
        assert result.status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT open_time FROM prospective_shadow_bar_receipts",
        ).fetchall() == [(decision_time.isoformat(),), (next_open.isoformat(),)]


def test_entry_bar_stop_is_checked_before_any_later_bar(tmp_path: Path) -> None:
    candle = replace(bar(), low=D(97), raw_low=D(97), candle_id="")
    at = candle.close_time
    first = entry()
    assessment = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(tmp_path / "entry_stop.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessment)
        with pytest.raises(ValueError, match="entry bar receipt"):
            positions.process_bar(
                trade_id, calendar=CAL,
                candle=replace(candle, source_revision="v2", candle_id=""),
                atr20=D(2), feature_known_at=OPEN, received_at=at, as_of=at,
            )
        stopped = positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at,
            trail_evidence=_trail_evidence(candle, damage=True),
        )
        assert stopped.status == "STOP_EXIT_MODELLED"
        assert stopped.source_candle_id == candle.candle_id
        assert stopped.known_at == at
        assert repo.connection.execute(
            "SELECT ordinal FROM prospective_shadow_bar_receipts",
        ).fetchall() == [(1,)]
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == [(trade_id,)]
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_structural_queues",
        ).fetchall() == []
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_trail_receipts",
        ).fetchall() == []


def test_max_hold_queue_fills_at_next_open_after_restart(tmp_path: Path) -> None:
    sessions = {}
    bars = []
    for day in range(6):
        start = OPEN + timedelta(days=day)
        sessions[start.date()] = (start, start + timedelta(hours=6, minutes=30))
        for slot in range(7):
            begin = start + timedelta(hours=slot)
            end = min(begin + timedelta(hours=1), sessions[start.date()][1])
            bars.append(replace(
                bar(), open_time=begin, close_time=end, session_date=start.date(),
                candle_id="",
            ))
    calendar = StaticSessionCalendar(sessions)
    first = entry()
    initial = bars[0]
    assessed = assess_entry(
        first, calendar=calendar, as_of=initial.close_time, candle=initial,
        received_at=initial.close_time,
    )
    path = tmp_path / "max_hold.sqlite"
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=calendar, as_of=initial.close_time, candle=initial,
            received_at=initial.close_time,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        for current in bars[:40]:
            result = positions.process_bar(
                trade_id, calendar=calendar, candle=current, atr20=D(2),
                feature_known_at=OPEN, received_at=current.close_time,
                as_of=current.close_time,
            )
            assert result.status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT reason, signal_ordinal, signal_candle_id "
            "FROM prospective_shadow_queued_exits WHERE trade_id = ?", (trade_id,),
        ).fetchone() == ("MAX_HOLD", 40, bars[39].candle_id)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute(
                "DELETE FROM prospective_shadow_queued_exits WHERE trade_id = ?", (trade_id,),
            )
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == []
        assert positions.process_bar(
            trade_id, calendar=calendar, candle=bars[39], atr20=D(2),
            feature_known_at=OPEN, received_at=bars[39].close_time,
            as_of=bars[39].close_time,
        ) == result
    exit_bar = replace(
        bars[40], open=D(105), high=D(106), low=D(104), close=D(105),
        raw_open=D(105), raw_high=D(106), raw_low=D(104), raw_close=D(105),
        candle_id="",
    )
    with SQLiteRepository(path) as repo:
        repo.migrate()
        positions = OfflineShadowPositions(repo)
        with pytest.raises(ValueError, match="unavailable"):
            positions.process_bar(
                trade_id, calendar=calendar, candle=exit_bar, atr20=D(2),
                feature_known_at=OPEN, received_at=exit_bar.close_time,
                as_of=bars[39].close_time,
            )
        result = positions.process_bar(
            trade_id, calendar=calendar, candle=exit_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=exit_bar.close_time,
            as_of=exit_bar.close_time,
        )
        assert isinstance(result, MaxHoldAssessment)
        assert result.status == "MAX_HOLD_EXIT_MODELLED"
        assert result.event_time == exit_bar.open_time
        assert result.known_at == exit_bar.close_time
        assert result.fill_price == D("104.96")
        assert not result.qualifying_completed_trade and not result.broker_write_performed
        assert positions.process_bar(
            trade_id, calendar=calendar, candle=exit_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=exit_bar.close_time,
            as_of=exit_bar.close_time,
        ) == result
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == [(trade_id,)]
        with pytest.raises(ValueError, match="already closed"):
            positions.process_bar(
                trade_id, calendar=calendar, candle=bars[41], atr20=D(2),
                feature_known_at=OPEN, received_at=bars[41].close_time,
                as_of=bars[41].close_time,
            )


def test_stop_on_fortieth_bar_takes_priority_over_max_hold(tmp_path: Path) -> None:
    sessions = {}
    bars = []
    for day in range(6):
        start = OPEN + timedelta(days=day)
        sessions[start.date()] = (start, start + timedelta(hours=6, minutes=30))
        for slot in range(7):
            begin = start + timedelta(hours=slot)
            bars.append(replace(
                bar(), open_time=begin,
                close_time=min(begin + timedelta(hours=1), sessions[start.date()][1]),
                session_date=start.date(), candle_id="",
            ))
    calendar = StaticSessionCalendar(sessions)
    first = entry()
    initial = bars[0]
    assessed = assess_entry(
        first, calendar=calendar, as_of=initial.close_time, candle=initial,
        received_at=initial.close_time,
    )
    with SQLiteRepository(tmp_path / "priority.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=calendar, as_of=initial.close_time, candle=initial,
            received_at=initial.close_time,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        for current in bars[:39]:
            assert positions.process_bar(
                trade_id, calendar=calendar, candle=current, atr20=D(2),
                feature_known_at=OPEN, received_at=current.close_time,
                as_of=current.close_time,
            ).status == "STOP_NOT_HIT"
        stop = replace(bars[39], low=D(97), raw_low=D(97), candle_id="")
        assert positions.process_bar(
            trade_id, calendar=calendar, candle=stop, atr20=D(2),
            feature_known_at=OPEN, received_at=stop.close_time,
            as_of=stop.close_time,
        ).status == "STOP_EXIT_MODELLED"
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_queued_exits",
        ).fetchall() == []


def _trail_evidence(candle: Candle, *, damage: bool = False) -> TrailEvidence:
    return TrailEvidence(
        adr20=D(4), adr_known_at=OPEN, ema20=None, ema_known_at=None,
        confirmed_swing=None, swing_known_at=None, prior_bar_extreme=None,
        prior_extreme_known_at=None,
        damage_inputs=DamageInputs(damage, damage, damage, False, False),
        damage_known_at=candle.close_time,
    )


def test_trail_stop_persists_and_applies_only_on_next_bar(tmp_path: Path) -> None:
    path = tmp_path / "trailed.sqlite"
    first = entry()
    candle = replace(bar(), high=D(103), raw_high=D(103), candle_id="")
    at = candle.close_time
    assessed = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        supplied = _trail_evidence(candle)
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, trail_evidence=supplied,
        ).status == "STOP_NOT_HIT"
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, trail_evidence=supplied,
        ).status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT ordinal, candle_id FROM prospective_shadow_trail_receipts",
        ).fetchall() == [(1, candle.candle_id)]
        stored_stop = repo.connection.execute(
            "SELECT json_extract(payload_json, '$.next_state.current_stop.__decimal__') "
            "FROM prospective_shadow_trail_receipts",
        ).fetchone()
        assert stored_stop is not None and D(stored_stop[0]) == D("99.836")
    stop = replace(
        bar(), open_time=at, close_time=at + timedelta(hours=1),
        low=D(99), raw_low=D(99), candle_id="",
    )
    with SQLiteRepository(path) as repo:
        repo.migrate()
        positions = OfflineShadowPositions(repo)
        result = positions.process_bar(
            trade_id, calendar=CAL, candle=stop, atr20=D(2), feature_known_at=OPEN,
            received_at=stop.close_time, as_of=stop.close_time,
        )
        assert result.status == "STOP_EXIT_MODELLED"
        assert result.fill_price == D("99.796")
        assert repo.connection.execute(
            "SELECT COUNT(*) FROM prospective_shadow_trail_receipts",
        ).fetchone() == (1,)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_shadow_trail_receipts")


def test_structural_queue_next_open_is_atomic_and_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "structural.sqlite"
    first = entry()
    candle = bar()
    at = candle.close_time
    assessed = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        supplied = _trail_evidence(candle, damage=True)
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, trail_evidence=supplied,
        ).status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT signal_ordinal, signal_candle_id "
            "FROM prospective_shadow_structural_queues",
        ).fetchall() == [(1, candle.candle_id)]
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == []
    next_bar = replace(
        bar(), open_time=at, close_time=at + timedelta(hours=1),
        open=D(102), high=D(103), low=D(101), close=D(102),
        raw_open=D(102), raw_high=D(103), raw_low=D(101), raw_close=D(102),
        candle_id="",
    )
    with SQLiteRepository(path) as repo:
        repo.migrate()
        positions = OfflineShadowPositions(repo)
        with pytest.raises(ValueError, match="unavailable"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
                feature_known_at=OPEN, received_at=next_bar.close_time, as_of=at,
            )
        result = positions.process_bar(
            trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        )
        assert isinstance(result, StructuralExitAssessment)
        assert result.event_time == next_bar.open_time
        assert result.known_at == next_bar.close_time
        assert result.fill_price == D("101.96")
        assert not result.qualifying_completed_trade and not result.broker_write_performed
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        ) == result
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == [(trade_id,)]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_shadow_structural_queues")


def test_surviving_shadow_trade_cannot_switch_trail_mode(tmp_path: Path) -> None:
    candle = bar()
    at = candle.close_time
    next_bar = replace(
        bar(), open_time=at, close_time=at + timedelta(hours=1),
        low=D(100), raw_low=D(100), candle_id="",
    )
    with SQLiteRepository(tmp_path / "mode.sqlite") as repo:
        repo.migrate()
        first = entry()
        assessed = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, trail_evidence=_trail_evidence(candle),
        ).status == "STOP_NOT_HIT"
        with pytest.raises(ValueError, match="mode cannot change"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
                feature_known_at=OPEN, received_at=next_bar.close_time,
                as_of=next_bar.close_time,
            )
        assert repo.connection.execute(
            "SELECT COUNT(*) FROM prospective_shadow_bar_receipts",
        ).fetchone() == (1,)


def test_structural_signal_at_bar_forty_precedes_max_hold(tmp_path: Path) -> None:
    sessions = {}
    bars = []
    for day in range(6):
        start = OPEN + timedelta(days=day)
        sessions[start.date()] = (start, start + timedelta(hours=6, minutes=30))
        for slot in range(7):
            begin = start + timedelta(hours=slot)
            bars.append(replace(
                bar(), open_time=begin,
                close_time=min(begin + timedelta(hours=1), sessions[start.date()][1]),
                session_date=start.date(), candle_id="",
            ))
    calendar = StaticSessionCalendar(sessions)
    first = entry()
    initial = bars[0]
    assessed = assess_entry(
        first, calendar=calendar, as_of=initial.close_time, candle=initial,
        received_at=initial.close_time,
    )
    with SQLiteRepository(tmp_path / "priority_managed.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=calendar, as_of=initial.close_time, candle=initial,
            received_at=initial.close_time,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        for ordinal, current in enumerate(bars[:40], 1):
            result = positions.process_bar(
                trade_id, calendar=calendar, candle=current, atr20=D(2),
                feature_known_at=OPEN, received_at=current.close_time,
                as_of=current.close_time,
                trail_evidence=_trail_evidence(current, damage=ordinal == 40),
            )
            assert result.status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT signal_ordinal FROM prospective_shadow_structural_queues",
        ).fetchall() == [(40,)]
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_queued_exits",
        ).fetchall() == []


def test_opposing_trap_signal_persists_and_exits_next_open_after_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "opposing_trap.sqlite"
    first = entry()
    candle = bar()
    at = candle.close_time
    assessed = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        trap = trap_evidence(candle.candle_id, at)
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, opposing_trap=trap,
        ).status == "STOP_NOT_HIT"
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, opposing_trap=trap,
        ).status == "STOP_NOT_HIT"
        with pytest.raises(ValueError, match="cannot be revised"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
                received_at=at, as_of=at,
            )
        assert repo.connection.execute(
            "SELECT signal_event_id, confidence FROM prospective_shadow_trap_queues",
        ).fetchall() == [("trap-1", "75")]
    next_bar = replace(
        bar(), open_time=at, close_time=at + timedelta(hours=1),
        open=D(102), high=D(103), low=D(101), close=D(102),
        raw_open=D(102), raw_high=D(103), raw_low=D(101), raw_close=D(102),
        candle_id="",
    )
    with SQLiteRepository(path) as repo:
        repo.migrate()
        positions = OfflineShadowPositions(repo)
        with pytest.raises(ValueError, match="unavailable"):
            positions.process_bar(
                trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
                feature_known_at=OPEN, received_at=next_bar.close_time, as_of=at,
            )
        result = positions.process_bar(
            trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        )
        assert isinstance(result, OpposingTrapExitAssessment)
        assert result.fill_price == D("101.96")
        assert result.event_time == next_bar.open_time
        assert not result.qualifying_completed_trade and not result.broker_write_performed
        assert positions.process_bar(
            trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        ) == result
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_shadow_trap_queues")


def test_structural_signal_precedes_opposing_trap(tmp_path: Path) -> None:
    candle = bar()
    at = candle.close_time
    first = entry()
    assessed = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(tmp_path / "trap_priority.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, trail_evidence=_trail_evidence(candle, damage=True),
            opposing_trap=trap_evidence(candle.candle_id, at),
        )
        assert repo.connection.execute(
            "SELECT signal_ordinal FROM prospective_shadow_structural_queues",
        ).fetchall() == [(1,)]
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_trap_queues",
        ).fetchall() == []


def test_managed_trap_exit_survives_restart_and_stop_has_priority(tmp_path: Path) -> None:
    path = tmp_path / "managed_trap.sqlite"
    candle = bar()
    at = candle.close_time
    first = entry()
    assessed = assess_entry(first, calendar=CAL, as_of=at, candle=candle, received_at=at)
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        positions.process_bar(
            trade_id, calendar=CAL, candle=candle, atr20=D(2), feature_known_at=OPEN,
            received_at=at, as_of=at, trail_evidence=_trail_evidence(candle),
            opposing_trap=trap_evidence(candle.candle_id, at),
        )
        assert repo.connection.execute(
            "SELECT signal_ordinal FROM prospective_shadow_trap_queues",
        ).fetchall() == [(1,)]
    next_bar = replace(
        bar(), open_time=at, close_time=at + timedelta(hours=1),
        open=D(102), high=D(103), low=D(101), close=D(102),
        raw_open=D(102), raw_high=D(103), raw_low=D(101), raw_close=D(102),
        candle_id="",
    )
    with SQLiteRepository(path) as repo:
        repo.migrate()
        result = OfflineShadowPositions(repo).process_bar(
            trade_id, calendar=CAL, candle=next_bar, atr20=D(2),
            feature_known_at=OPEN, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        )
        assert isinstance(result, OpposingTrapExitAssessment)

    stop_candle = replace(
        bar(), low=D(97), raw_low=D(97), candle_id="",
    )
    with SQLiteRepository(tmp_path / "stop_priority.sqlite") as repo:
        repo.migrate()
        assessed = assess_entry(
            first, calendar=CAL, as_of=at, candle=stop_candle, received_at=at,
        )
        ProspectiveEntryRegistry(repo).assess(
            first, calendar=CAL, as_of=at, candle=stop_candle, received_at=at,
        )
        positions = OfflineShadowPositions(repo)
        trade_id = positions.open(first, assessed)
        result = positions.process_bar(
            trade_id, calendar=CAL, candle=stop_candle, atr20=D(2),
            feature_known_at=OPEN, received_at=at, as_of=at,
            opposing_trap=trap_evidence(stop_candle.candle_id, at),
        )
        assert result.status == "STOP_EXIT_MODELLED"
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_trap_queues",
        ).fetchall() == []
