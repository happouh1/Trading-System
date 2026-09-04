from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.unit.test_phase7b_range_research import replay, research_bars
from tests.unit.test_phase7c_range_experiment import materialization

from trading_system.patterns import RangeExperimentRegistry, RangeResearchRegistry
from trading_system.persistence import RunRecord, SQLiteRepository


def test_phase7c_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "range-experiment.sqlite"
    run = RunRecord(
        "range-research-run",
        datetime(2024, 8, 1, tzinfo=UTC),
        "test",
        "sha256:test",
        "fixture-v1",
        "XNYS-v1",
        0,
    )
    research = replay().run(research_bars())
    experiment = materialization()
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        RangeResearchRegistry(repository).persist(run.run_id, research)
        registry = RangeExperimentRegistry(repository)
        inserted = registry.persist(run.run_id, experiment)
        assert inserted == (1, len(experiment.assignments), len(experiment.gates))
        assert registry.persist(run.run_id, experiment) == (0, 0, 0)
        expected = registry.counts(experiment.plan.plan_id)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert RangeExperimentRegistry(repository).counts(experiment.plan.plan_id) == expected
