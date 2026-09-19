from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_prospective_entry import CAL, OPEN, D, bar, entry

from trading_system.execution_sim.prospective import assess_entry
from trading_system.execution_sim.prospective_positions import OfflineShadowPositions
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
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
        stopped = positions.close_stop(
            trade_id, candle=stop_bar, atr20=D(2), feature_known_at=OPEN,
            received_at=stop_bar.close_time, as_of=stop_bar.close_time,
        )
        assert stopped is not None and stopped.status == "STOP_EXIT_MODELLED"
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
        with pytest.raises(ValueError, match="already closed"):
            positions.close_stop(
                trade_id, candle=stop_bar, atr20=D(2), feature_known_at=OPEN,
                received_at=stop_bar.close_time, as_of=stop_bar.close_time,
            )
        for table in ("prospective_shadow_positions", "prospective_shadow_exit_receipts"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                repo.connection.execute(f"DELETE FROM {table}")
    with SQLiteRepository(path) as repo:
        repo.migrate()
        assert repo.connection.execute(
            "SELECT trade_id FROM prospective_shadow_exit_receipts",
        ).fetchall() == [(trade_id,)]
