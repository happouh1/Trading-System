from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import ExperimentSpec, WalkForwardSpec
from trading_system.research.orchestration import CohortSpec, ExperimentStage
from trading_system.research.registry import ExperimentRegistry
from trading_system.research.workflow import ExperimentWorkflow


def experiment() -> ExperimentSpec:
    return ExperimentSpec(
        "experiment-2b",
        datetime(2026, 1, 1, tzinfo=UTC),
        ("run-1",),
        "code-1",
        ("config-1",),
        ("data-1",),
        ("calendar-1",),
        "universe-1",
        WalkForwardSpec(4, 2, 2, 2, 1),
        "metrics-1",
        "similarity-1",
        7,
    )


def test_workflow_enforces_freeze_and_survives_restart(tmp_path: Path) -> None:
    database = tmp_path / "research.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = ExperimentRegistry(repository)
        registry.insert_experiment(experiment())
        registry.insert_cohort(CohortSpec("all", "experiment-2b", "all"))
        workflow = ExperimentWorkflow(registry, "experiment-2b")
        now = datetime(2026, 1, 2, tzinfo=UTC)
        workflow.advance(ExperimentStage.TRAIN_EVALUATED, occurred_at=now)
        workflow.advance(ExperimentStage.VALIDATION_EVALUATED, occurred_at=now)
        with pytest.raises(ValueError, match="invalid"):
            workflow.advance(ExperimentStage.TEST_EVALUATED, occurred_at=now)
        workflow.advance(
            ExperimentStage.FROZEN,
            frozen_definition_hash="sha256:frozen",
            occurred_at=now,
        )
        with pytest.raises(ValueError, match="after freeze"):
            registry.insert_cohort(CohortSpec("late", "experiment-2b", "late"))
    with SQLiteRepository(database) as repository:
        repository.migrate()
        workflow = ExperimentWorkflow(ExperimentRegistry(repository), "experiment-2b")
        assert workflow.stage is ExperimentStage.FROZEN
        assert workflow.advance(
            ExperimentStage.TEST_EVALUATED,
            occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
