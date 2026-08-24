from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit.test_features import daily_candle

from trading_system.domain import (
    Decision,
    DecisionAction,
    Direction,
    Timeframe,
    TradePlan,
    TradeStyle,
)
from trading_system.features import CausalFeatureEngine
from trading_system.market_data import StaticSessionCalendar
from trading_system.paper import (
    InternalSimulatorAdapter,
    PaperMode,
    PaperRegistry,
    PaperRuntime,
    PaperSession,
    stage_shadow_decision,
)
from trading_system.persistence import RunRecord, SQLiteRepository

D = Decimal


def test_directional_decision_stages_one_causal_shadow_intent(tmp_path: Path) -> None:
    database = tmp_path / "bridge.sqlite"
    candle = daily_candle(0)
    run = RunRecord(
        "bridge-run", datetime(2026, 1, 1, tzinfo=UTC), "git:test",
        "strategy-config", "data-v1", "fixture-v1", 7,
    )
    observation = CausalFeatureEngine(run.run_id).push(candle)
    plan = TradePlan(
        "bridge-plan", "AAPL", Timeframe.HOUR_1, Direction.LONG,
        candle.close_time, D("101"), D("99"), D("2"), D("2"), D("2"),
        "bridge-pattern",
    )
    decision = Decision(
        "bridge-decision", run.run_id, observation.observation_id, candle.close_time,
        DecisionAction.LONG, Direction.LONG, D("80"), D("80"), D("80"),
        TradeStyle.CONTINUATION, plan,
    )
    next_open = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    calendar = StaticSessionCalendar({
        date(2026, 1, 2): (next_open, datetime(2026, 1, 2, 21, tzinfo=UTC))
    })
    staged_at = datetime(2026, 1, 1, 22, tzinfo=UTC)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        repository.insert_decision(decision)
        paper = PaperRegistry(repository)
        paper.insert_session(
            PaperSession(
                "bridge-session", staged_at, PaperMode.SHADOW, "git:test",
                "paper-config", "data-v1", "fixture-v1",
            )
        )
        PaperRuntime(
            paper, "bridge-session", PaperMode.SHADOW, InternalSimulatorAdapter()
        ).start(staged_at)
        first = stage_shadow_decision(
            repository, "bridge-session", decision.decision_id, staged_at, calendar
        )
        second = stage_shadow_decision(
            repository, "bridge-session", decision.decision_id, staged_at, calendar
        )
        assert first == second
        assert first.scheduled_open == next_open
        assert first.payload["source_decision_id"] == decision.decision_id
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM paper_intents"
        ).fetchone() == (1,)
        assert repository.connection.execute(
            "SELECT COUNT(*) FROM paper_adapter_events"
        ).fetchone() == (0,)
        with pytest.raises(ValueError, match="stale"):
            stage_shadow_decision(
                repository, "bridge-session", decision.decision_id, next_open, calendar
            )
        mismatched_calendar = StaticSessionCalendar(
            {date(2026, 1, 2): (next_open, datetime(2026, 1, 2, 21, tzinfo=UTC))},
            version="different-calendar",
        )
        with pytest.raises(ValueError, match="calendar version"):
            stage_shadow_decision(
                repository,
                "bridge-session",
                decision.decision_id,
                staged_at,
                mismatched_calendar,
            )
