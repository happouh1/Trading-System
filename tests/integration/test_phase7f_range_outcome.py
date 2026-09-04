from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tests.unit.test_features import daily_candle
from tests.unit.test_phase7d_range_trigger import accepted_event, range_box
from tests.unit.test_phase7d_range_trigger import config as trigger_config
from tests.unit.test_phase7e_range_entry import config as entry_config
from tests.unit.test_phase7f_range_outcome import config as outcome_config

from trading_system.domain import Observation
from trading_system.patterns import (
    RangeEntryContext,
    RangeEntryRegistry,
    RangeOutcomeRegistry,
    RangeResearchRegistry,
    RangeTriggerRegistry,
    compose_range_reclaim_evidence,
    label_range_entries,
    materialize_range_entries,
)
from trading_system.persistence import RunRecord, SQLiteRepository


def test_phase7f_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "range-outcome.sqlite"
    box = range_box()
    event_candle = daily_candle(48)
    event = replace(
        accepted_event(), observation_id="observation-7f", known_at=event_candle.close_time,
        evidence_candle_ids=(event_candle.candle_id,),
    )
    observation = Observation(
        "observation-7f", "run-7d", event_candle.candle_id, event_candle.close_time,
        "1.0.0", "fixture-fingerprint", {}, {"complete": True},
    )
    evidence = compose_range_reclaim_evidence(
        trigger_config(), boxes=(box,), events=(event,)
    )[0]
    entry_candle = replace(daily_candle(49), open=Decimal("99"), raw_open=Decimal("99"))
    context = RangeEntryContext(
        evidence.evidence_id, evidence.known_at, Decimal("2"), Decimal("2")
    )
    entry = materialize_range_entries(
        entry_config(), evidence=(evidence,), contexts=(context,), candles=(entry_candle,)
    )[0]
    candles = (entry_candle, daily_candle(50), daily_candle(51))
    outcome = label_range_entries(
        outcome_config(), entries=(entry,), boxes=(box,), candles=candles
    )[0]
    run = RunRecord(
        "run-7d", datetime(2026, 1, 1, tzinfo=UTC), "test", "sha256:test",
        "fixture-v1", "XNYS-v1", 0,
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        for candle in (event_candle, *candles):
            repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        repository.insert_pattern_event(event)
        RangeResearchRegistry(repository).insert_box(run.run_id, box)
        RangeTriggerRegistry(repository).persist(evidence)
        RangeEntryRegistry(repository).persist(entry)
        registry = RangeOutcomeRegistry(repository)
        assert registry.persist(outcome)
        assert not registry.persist(outcome)
        assert registry.count(run.run_id) == 1
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert RangeOutcomeRegistry(repository).count(run.run_id) == 1
