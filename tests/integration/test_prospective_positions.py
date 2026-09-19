from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_prospective_entry import CAL, OPEN, D, bar, entry

from trading_system.domain import Timeframe
from trading_system.execution_sim.prospective import assess_entry
from trading_system.execution_sim.prospective_positions import OfflineShadowPositions
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.market_data.calendar import StaticSessionCalendar
from trading_system.persistence import SQLiteRepository


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
        result = positions.process_bar(
            trade_id, calendar=CAL, candle=hold, atr20=D(2), feature_known_at=OPEN,
            received_at=hold.close_time, as_of=hold.close_time,
        )
        assert result.status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT ordinal, candle_id FROM prospective_shadow_bar_receipts",
        ).fetchall() == [(1, hold.candle_id)]
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
        ).fetchall() == [(1,), (2,)]


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
        result = positions.process_bar(
            trade_id, calendar=calendar, candle=next_bar, atr20=D(2),
            feature_known_at=decision_time, received_at=next_bar.close_time,
            as_of=next_bar.close_time,
        )
        assert result.status == "STOP_NOT_HIT"
        assert repo.connection.execute(
            "SELECT open_time FROM prospective_shadow_bar_receipts",
        ).fetchall() == [(next_open.isoformat(),)]
