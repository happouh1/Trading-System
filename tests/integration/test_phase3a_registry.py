from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trading_system.modeling.contracts import ModelExperiment, ModelStage
from trading_system.modeling.registry import ModelRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import ExperimentSpec, WalkForwardFold, WalkForwardSpec
from trading_system.research.registry import ExperimentRegistry


def research_experiment() -> ExperimentSpec:
    return ExperimentSpec(
        "research-1",
        datetime(2026, 1, 1, tzinfo=UTC),
        ("run-1",),
        "code",
        ("config",),
        ("data",),
        ("calendar",),
        "universe",
        WalkForwardSpec(),
        "metric",
        "similarity",
        7,
    )


def model_experiment() -> ModelExperiment:
    return ModelExperiment(
        "model-1",
        "research-1",
        datetime(2026, 1, 2, tzinfo=UTC),
        "sha256:dataset",
        "sha256:features",
        "target-1",
        "logistic-1",
        "sha256:config",
        "code",
        {"scikit-learn": "1.5"},
        7,
    )


def test_model_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "models.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        research = ExperimentRegistry(repository)
        research.insert_experiment(research_experiment())
        research.insert_fold(
            WalkForwardFold(
                "fold-1",
                "research-1",
                0,
                date(2020, 1, 1),
                date(2021, 12, 31),
                date(2022, 1, 10),
                date(2022, 3, 31),
                date(2022, 4, 10),
                date(2022, 6, 30),
            )
        )
        registry = ModelRegistry(repository)
        source = model_experiment()
        assert registry.insert_experiment(source)
        assert not registry.insert_experiment(source)
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_experiment(replace(source, seed=8))
        now = datetime(2026, 1, 3, tzinfo=UTC)
        registry.transition(source.model_experiment_id, ModelStage.TRAINED, now)
        registry.transition(source.model_experiment_id, ModelStage.VALIDATION_EVALUATED, now)
        with pytest.raises(ValueError, match="invalid"):
            registry.transition(source.model_experiment_id, ModelStage.TEST_EVALUATED, now)
        registry.transition(
            source.model_experiment_id,
            ModelStage.FROZEN,
            now,
            frozen_manifest_hash="sha256:frozen",
        )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert ModelRegistry(repository).current_stage("model-1") is ModelStage.FROZEN
