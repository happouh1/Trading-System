from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from tests.unit.test_features import daily_candle
from tests.unit.test_phase7d_range_trigger import accepted_event, config, range_box

from trading_system.domain import Observation
from trading_system.patterns import (
    RangeResearchRegistry,
    RangeTriggerRegistry,
    compose_range_reclaim_evidence,
)
from trading_system.persistence import RunRecord, SQLiteRepository


def test_phase7d_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "range-trigger.sqlite"
    box = range_box()
    candle = daily_candle(48)
    event = accepted_event(hours_after=24)
    event = replace(
        event,
        observation_id="observation-7d",
        known_at=candle.close_time,
        evidence_candle_ids=(candle.candle_id,),
    )
    observation = Observation(
        "observation-7d",
        "run-7d",
        candle.candle_id,
        candle.close_time,
        "1.0.0",
        "fixture-fingerprint",
        {},
        {"complete": True},
    )
    evidence = compose_range_reclaim_evidence(config(), boxes=(box,), events=(event,))[0]
    run = RunRecord(
        "run-7d", datetime(2026, 1, 1, tzinfo=UTC), "test", "sha256:test",
        "fixture-v1", "XNYS-v1", 0,
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        repository.insert_pattern_event(event)
        RangeResearchRegistry(repository).insert_box(run.run_id, box)
        registry = RangeTriggerRegistry(repository)
        assert registry.persist(evidence)
        assert not registry.persist(evidence)
        assert registry.count(run.run_id) == 1
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert RangeTriggerRegistry(repository).count(run.run_id) == 1
