from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tests.unit.test_features import daily_candle
from tests.unit.test_phase7b_range_research import replay, research_bars
from tests.unit.test_phase7c_range_experiment import materialization
from tests.unit.test_phase7d_range_trigger import accepted_event, range_box
from tests.unit.test_phase7d_range_trigger import config as trigger_config
from tests.unit.test_phase7e_range_entry import config as entry_config
from tests.unit.test_phase7f_range_outcome import config as outcome_config

from trading_system.domain import Observation
from trading_system.patterns import (
    RangeEntryContext,
    RangeEntryRegistry,
    RangeEvaluationRegistry,
    RangeExperimentRegistry,
    RangeOutcomeRegistry,
    RangeResearchRegistry,
    RangeTriggerRegistry,
    compose_range_reclaim_evidence,
    evaluate_range_outcomes,
    label_range_entries,
    load_range_evaluation_config,
    materialize_range_entries,
)
from trading_system.persistence import RunRecord, SQLiteRepository

ROOT = Path(__file__).parents[2]


def test_phase7g_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "range-evaluation.sqlite"
    run = RunRecord(
        "run-7d",
        datetime(2024, 8, 1, tzinfo=UTC),
        "test",
        "sha256:test",
        "fixture-v1",
        "XNYS-v1",
        0,
    )
    experiment = materialization()
    box = range_box()
    event_candle = daily_candle(48)
    event = replace(
        accepted_event(),
        observation_id="observation-7g",
        known_at=event_candle.close_time,
        evidence_candle_ids=(event_candle.candle_id,),
    )
    observation = Observation(
        "observation-7g",
        run.run_id,
        event_candle.candle_id,
        event_candle.close_time,
        "1.0.0",
        "fixture-fingerprint",
        {},
        {"complete": True},
    )
    evidence = compose_range_reclaim_evidence(
        trigger_config(), boxes=(box,), events=(event,)
    )[0]
    entry_candle = replace(daily_candle(49), open=Decimal("99"), raw_open=Decimal("99"))
    entry = materialize_range_entries(
        entry_config(),
        evidence=(evidence,),
        contexts=(
            RangeEntryContext(
                evidence.evidence_id, evidence.known_at, Decimal("2"), Decimal("2")
            ),
        ),
        candles=(entry_candle,),
    )[0]
    outcome = label_range_entries(
        outcome_config(),
        entries=(entry,),
        boxes=(box,),
        candles=(entry_candle, daily_candle(50), daily_candle(51)),
    )[0]
    evaluation = evaluate_range_outcomes(
        load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml"),
        experiment=experiment,
        outcomes=(outcome,),
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        RangeResearchRegistry(repository).persist(run.run_id, replay().run(research_bars()))
        RangeExperimentRegistry(repository).persist(run.run_id, experiment)
        for candle in (event_candle, entry_candle, daily_candle(50), daily_candle(51)):
            repository.insert_candle(candle)
        repository.insert_snapshot(observation)
        repository.insert_pattern_event(event)
        RangeTriggerRegistry(repository).persist(evidence)
        RangeEntryRegistry(repository).persist(entry)
        RangeOutcomeRegistry(repository).persist(outcome)
        registry = RangeEvaluationRegistry(repository)
        expected = (len(evaluation.assignments), len(evaluation.summaries))
        assert registry.persist(evaluation) == expected
        assert registry.persist(evaluation) == (0, 0)
        assert registry.counts(experiment.plan.plan_id) == expected
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert RangeEvaluationRegistry(repository).counts(experiment.plan.plan_id) == expected
