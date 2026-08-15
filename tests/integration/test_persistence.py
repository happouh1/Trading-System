from __future__ import annotations

from datetime import UTC, datetime
import sqlite3
from pathlib import Path

import pytest

from trading_system.features import CausalFeatureEngine
from trading_system.persistence import RunRecord, SQLiteRepository
from tests.unit.test_features import daily_candle


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
