from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.test_features import daily_candle

from trading_system.domain import (
    Direction,
    Level,
    LevelKind,
    PatternEvent,
    PatternState,
)
from trading_system.features import CausalFeatureEngine
from trading_system.persistence import RunRecord, SQLiteRepository


def test_migration_persistence_and_restart_are_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "phase1a.sqlite"
    run = RunRecord(
        run_id="run-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        code_version="git:test",
        config_hash="sha256:config",
        data_revision="sha256:features-v1",
        calendar_version="fixture-v1",
        random_seed=20260101,
    )
    candle = daily_candle(0)
    observation = CausalFeatureEngine(run.run_id).push(candle)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert repository.insert_run(run)
        assert repository.insert_candle(candle)
        assert repository.insert_snapshot(observation)
        assert repository.counts() == (1, 1, 1)
    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        assert not restarted.insert_run(run)
        assert not restarted.insert_candle(candle)
        assert not restarted.insert_snapshot(observation)
        assert restarted.counts() == (1, 1, 1)


def test_foreign_keys_reject_orphan_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "foreign-key.sqlite"
    observation = CausalFeatureEngine("missing-run").push(daily_candle(0))
    with SQLiteRepository(database) as repository:
        repository.migrate()
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            repository.insert_snapshot(observation)


def test_phase1b_events_are_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "phase1b.sqlite"
    run = RunRecord(
        run_id="run-1",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        code_version="git:test",
        config_hash="sha256:config",
        data_revision="sha256:data",
        calendar_version="fixture-v1",
        random_seed=20260101,
    )
    candle = daily_candle(0)
    observation = CausalFeatureEngine(run.run_id).push(candle)
    level = Level(
        level_id="level-1",
        run_id=run.run_id,
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        known_at=candle.close_time,
        lower_price=Decimal("99"),
        upper_price=Decimal("101"),
        kind=LevelKind.BASE_BOUNDARY,
        confluence_score=Decimal("50"),
        evidence_candle_ids=(candle.candle_id,),
    )
    event = PatternEvent(
        event_id="event-1",
        run_id=run.run_id,
        observation_id=observation.observation_id,
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        known_at=candle.close_time,
        pattern_family="BREAKOUT",
        pattern_name="BASE_BREAKOUT",
        pattern_version="1.0.0",
        instance_id="instance-1",
        prior_state=None,
        new_state=PatternState.CANDIDATE,
        direction=Direction.LONG,
        reference_level=level.upper_price,
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        assert repository.insert_level(level)
        assert repository.insert_pattern_event(event)
        assert not repository.insert_level(level)
        assert not repository.insert_pattern_event(event)
        counts = repository.connection.execute(
            "SELECT (SELECT COUNT(*) FROM levels), (SELECT COUNT(*) FROM pattern_events)"
        ).fetchone()
        assert counts == (1, 1)
