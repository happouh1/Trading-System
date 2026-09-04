from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.unit.test_phase7b_range_research import replay, research_bars

from trading_system.patterns import RangeResearchRegistry
from trading_system.persistence import RunRecord, SQLiteRepository


def test_range_research_persistence_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "range.sqlite"
    run = RunRecord(
        run_id="range-research-run",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        code_version="test",
        config_hash="sha256:test",
        data_revision="fixture-v1",
        calendar_version="XNYS-v1",
        random_seed=0,
    )
    result = replay().run(research_bars())
    with SQLiteRepository(database) as repository:
        repository.migrate()
        repository.insert_run(run)
        registry = RangeResearchRegistry(repository)
        inserted = registry.persist(run.run_id, result)
        assert inserted == (len(result.boxes), len(result.outcomes))
        assert registry.persist(run.run_id, result) == (0, 0)
        expected = registry.counts(run.run_id)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert RangeResearchRegistry(repository).counts(run.run_id) == expected


def test_range_research_requires_a_persisted_run(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "range.sqlite") as repository:
        repository.migrate()
        registry = RangeResearchRegistry(repository)
        result = replay().run(research_bars(1))
        try:
            registry.persist("missing", result)
        except ValueError as exc:
            assert "run must be persisted" in str(exc)
        else:
            raise AssertionError("missing run should fail closed")
