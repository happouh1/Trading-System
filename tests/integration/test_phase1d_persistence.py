from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tests.unit.test_features import daily_candle

from trading_system.backtest import complete_trade
from trading_system.domain import Direction, Observation
from trading_system.learning import label_outcome
from trading_system.persistence import RunRecord, SQLiteRepository
from trading_system.replay import ReplayOrchestrator


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


def test_replay_orchestrator_persists_one_decision_per_candle(tmp_path: Path) -> None:
    path = tmp_path / "replay.sqlite"
    run = RunRecord("run-2", datetime(2026, 1, 1, tzinfo=UTC), "code", "cfg", "data", "cal", 1)
    candles = tuple(daily_candle(index) for index in range(3))
    with SQLiteRepository(path) as repository:
        repository.migrate()
        repository.insert_run(run)
        summary = ReplayOrchestrator(run.run_id, repository).run(candles)
        assert summary.processed_candles == 3
        assert repository.run_counts(run.run_id)["decisions"] == 3
        rows = repository.observation_export_rows(run.run_id)
        assert len(rows) == 3
        assert all(row["config_hash"] == "cfg" for row in rows)


def test_replay_resume_rebuilds_causal_feature_warmup(tmp_path: Path) -> None:
    path = tmp_path / "resume.sqlite"
    run = RunRecord("run-3", datetime(2026, 1, 1, tzinfo=UTC), "code", "cfg", "data", "cal", 1)
    candles = tuple(daily_candle(index) for index in range(3))
    with SQLiteRepository(path) as repository:
        repository.migrate()
        repository.insert_run(run)
        first = ReplayOrchestrator(run.run_id, repository).run(candles[:2])
        assert first.checkpoint is not None
        resumed = ReplayOrchestrator(run.run_id, repository).run(
            candles,
            resume_after=first.checkpoint.last_close_time,
            processed_before=first.checkpoint.processed_candles,
            prior_state_hash=first.checkpoint.state_hash,
        )
        assert resumed.processed_candles == 1
        assert resumed.checkpoint is not None
        assert resumed.checkpoint.processed_candles == 3

    full_path = tmp_path / "full.sqlite"
    full_run = RunRecord(
        "run-3",
        datetime(2026, 1, 1, tzinfo=UTC),
        "code",
        "cfg",
        "data",
        "cal",
        1,
    )
    with SQLiteRepository(full_path) as repository:
        repository.migrate()
        repository.insert_run(full_run)
        full = ReplayOrchestrator(full_run.run_id, repository).run(candles)
        assert full.checkpoint is not None
        assert resumed.checkpoint.state_hash == full.checkpoint.state_hash


def test_completed_trade_metrics_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "trades.sqlite"
    run = RunRecord("run-4", datetime(2026, 1, 1, tzinfo=UTC), "code", "cfg", "data", "cal", 1)
    trade = complete_trade(
        trade_id="trade-1",
        run_id=run.run_id,
        symbol="AAPL",
        timeframe=daily_candle(0).timeframe,
        direction=Direction.LONG,
        entry_time=daily_candle(0).open_time,
        exit_time=daily_candle(1).close_time,
        entry_price=Decimal("100"),
        exit_price=Decimal("104"),
        initial_risk=Decimal("2"),
        favorable_extreme=Decimal("105"),
        adverse_extreme=Decimal("99"),
        hold_bars=2,
        total_cost=Decimal("0.20"),
    )
    with SQLiteRepository(path) as repository:
        repository.migrate()
        repository.insert_run(run)
        assert repository.insert_completed_trade(trade)
        assert not repository.insert_completed_trade(trade)
        results = repository.trade_results(run.run_id)
        assert len(results) == 1
        assert results[0].net_r == Decimal("1.9")
