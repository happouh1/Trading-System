from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tests.unit.test_features import daily_candle
from trading_system.domain import Direction, Observation
from trading_system.learning import label_outcome
from trading_system.persistence import RunRecord, SQLiteRepository


def test_checkpoint_restart_and_outcome_idempotence(tmp_path: Path) -> None:
    path = tmp_path / "phase1d.sqlite"
    run = RunRecord("run-1", datetime(2026, 1, 1, tzinfo=UTC), "code", "cfg", "data", "cal", 1)
    candle = daily_candle(0)
    observation = Observation(
        observation_id="observation-1",
        run_id=run.run_id,
        candle_id=candle.candle_id,
        known_at=candle.close_time,
        schema_version="1.0.0",
        input_fingerprint="fingerprint",
        features={},
        data_quality={},
    )
    future = (daily_candle(1),)
    outcome = label_outcome(
        run_id=run.run_id,
        observation_id=observation.observation_id,
        label_version="1.0.0",
        direction=Direction.LONG,
        entry=Decimal("100"),
        risk=Decimal("2"),
        future_candles=future,
    )
    with SQLiteRepository(path) as repository:
        repository.migrate()
        repository.insert_run(run)
        repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        assert repository.insert_outcome(outcome)
        assert not repository.insert_outcome(outcome)
        repository.save_checkpoint(run.run_id, candle.close_time, 1, "sha256:state")
    with SQLiteRepository(path) as repository:
        repository.migrate()
        checkpoint = repository.load_checkpoint(run.run_id)
        assert checkpoint == (candle.close_time, 1, "sha256:state")
