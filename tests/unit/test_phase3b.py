from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.domain import Candle, Direction, Timeframe, TradePlan
from trading_system.paper import (
    CompletedBarEnvelope,
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    RuntimeState,
    load_paper_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)


def plan() -> TradePlan:
    return TradePlan(
        "plan-1", "AAPL", Timeframe.HOUR_1, Direction.LONG, NOW,
        Decimal("101"), Decimal("99"), Decimal("2"), Decimal("1.5"),
        Decimal("2"), "pattern-1",
    )


def session(mode: PaperMode = PaperMode.SHADOW) -> PaperSession:
    return PaperSession("paper-1", NOW, mode, "code", "config", "data", "XNYS")


def candle(candle_id: str, close_time: datetime) -> Candle:
    return Candle(
        "AAPL", Timeframe.HOUR_1, close_time - timedelta(hours=1), close_time,
        date(2026, 1, 5), Decimal("100"), Decimal("102"), Decimal("99"),
        Decimal("101"), Decimal("1000"), True, Decimal("1"), "fixture", "revision-1",
        candle_id,
    )


def test_config_is_strict_and_versioned() -> None:
    config = load_paper_config(ROOT / "config/paper.phase3b.v1.yaml")
    assert config.config_hash.startswith("sha256:")
    assert config.values["default_mode"] == "SHADOW"


def test_naive_contract_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PaperSession("paper", datetime(2026, 1, 1), PaperMode.SHADOW,
                     "code", "config", "data", "calendar")


def test_shadow_never_submits_and_duplicate_plan_is_idempotent(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "paper.sqlite") as repository:
        repository.migrate()
        registry = PaperRegistry(repository)
        registry.insert_session(session())
        adapter = InternalSimulatorAdapter()
        runtime = PaperRuntime(registry, "paper-1", PaperMode.SHADOW, adapter)
        assert runtime.start(NOW) is RuntimeState.SHADOW
        first = runtime.record_plan(plan(), NOW + timedelta(hours=1), NOW)
        second = runtime.record_plan(
            plan(), NOW + timedelta(hours=1), NOW + timedelta(seconds=30)
        )
        assert first.intent_id == second.intent_id
        assert not adapter.order_ids()
        count = repository.connection.execute("SELECT COUNT(*) FROM paper_intents").fetchone()
        assert count == (1,)


def test_simulated_submission_reconciles_and_halt_blocks_intents(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "paper.sqlite") as repository:
        repository.migrate()
        registry = PaperRegistry(repository)
        registry.insert_session(session(PaperMode.SIMULATED))
        adapter = InternalSimulatorAdapter()
        runtime = PaperRuntime(registry, "paper-1", PaperMode.SIMULATED, adapter)
        assert runtime.start(NOW) is RuntimeState.PAPER_ENABLED
        runtime.record_plan(plan(), NOW + timedelta(hours=1), NOW)
        assert runtime.reconcile(NOW + timedelta(seconds=1)).matched
        runtime.halt(NOW + timedelta(seconds=2), "MANUAL")
        with pytest.raises(ValueError, match="not accepting"):
            runtime.record_plan(plan(), NOW + timedelta(hours=2), NOW)


def test_completed_bar_checkpoint_recovers_and_stale_data_halts(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    close_time = NOW + timedelta(hours=1)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = PaperRegistry(repository)
        registry.insert_session(session())
        runtime = PaperRuntime(registry, "paper-1", PaperMode.SHADOW,
                               InternalSimulatorAdapter())
        runtime.start(NOW)
        envelope = CompletedBarEnvelope(candle("bar-1", close_time), close_time, "revision-1")
        state_hash = runtime.process_completed_bar(envelope, close_time)
        runtime.heartbeat(close_time)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = PaperRegistry(repository)
        assert registry.latest_checkpoint("paper-1") == (
            close_time, state_hash, Timeframe.HOUR_1.value,
        )
        runtime = PaperRuntime(registry, "paper-1", PaperMode.SHADOW,
                               InternalSimulatorAdapter())
        with pytest.raises(ValueError, match="stale"):
            runtime.process_completed_bar(
                CompletedBarEnvelope(
                    candle("bar-2", close_time + timedelta(hours=1)),
                    close_time + timedelta(hours=1, seconds=121), "revision-1",
                ),
                close_time + timedelta(hours=1, seconds=121),
            )
        assert registry.current_state("paper-1") is RuntimeState.HALTED
