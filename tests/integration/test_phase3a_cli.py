from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from trading_system.cli import main
from trading_system.modeling.registry import ModelRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import ExperimentSpec, WalkForwardFold, WalkForwardSpec
from trading_system.research.registry import ExperimentRegistry
from trading_system.serialization import canonical_hash


def _write_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "model_version": "3A.1.0",
                "target": {
                    "name": "GENERIC_2R_BEFORE_1R",
                    "positive_labels": ["GENERIC_SUCCESS"],
                    "negative_labels": ["GENERIC_FAILURE"],
                },
                "numeric_features": ["trend_score"],
                "categorical_features": ["pattern"],
                "estimator": {
                    "kind": "L2_LOGISTIC_REGRESSION",
                    "c": 1.0,
                    "max_iter": 2000,
                    "class_weight": "balanced",
                    "solver": "liblinear",
                },
                "calibration": {"method": "sigmoid", "minimum_class_count": 3},
                "diagnostic_thresholds": [0.5, 0.6, 0.7],
                "bootstrap_samples": 100,
                "minimum_breakdown_sample": 30,
                "determinism": {"seed": 7, "jobs": 1},
            }
        ),
        encoding="utf-8",
    )


def _write_dataset(path: Path) -> None:
    rows: list[dict[str, object]] = []
    values = (
        ("TRAIN", 20, "GENERIC_FAILURE"),
        ("TRAIN", 25, "GENERIC_FAILURE"),
        ("TRAIN", 30, "GENERIC_FAILURE"),
        ("TRAIN", 70, "GENERIC_SUCCESS"),
        ("TRAIN", 75, "GENERIC_SUCCESS"),
        ("TRAIN", 80, "GENERIC_SUCCESS"),
        ("VALIDATION", 35, "GENERIC_FAILURE"),
        ("VALIDATION", 65, "GENERIC_SUCCESS"),
        ("TEST", 40, "GENERIC_FAILURE"),
        ("TEST", 60, "GENERIC_SUCCESS"),
    )
    for index, (partition, trend, label) in enumerate(values):
        rows.append(
            {
                "row_id": f"row-{index}",
                "observation_id": f"observation-{index}",
                "fold_id": "fold-1",
                "partition": partition,
                "label_available_at": "2026-01-01T00:00:00Z",
                "outcome_label": label,
                "features": {"trend_score": trend, "pattern": "BREAKOUT"},
            }
        )
    path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")


def test_complete_phase3a_cli_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "model.sqlite"
    config = tmp_path / "model.json"
    dataset = tmp_path / "model.jsonl"
    manifest = tmp_path / "manifest.json"
    artifacts = tmp_path / "artifacts"
    report = tmp_path / "report.md"
    _write_config(config)
    _write_dataset(dataset)
    manifest.write_text(
        json.dumps(
            {
                "model_experiment_id": "model-cli",
                "research_experiment_id": "research-cli",
                "created_at": "2026-01-01T00:00:00Z",
                "code_version": "test",
                "dependency_versions": {"scikit-learn": "test"},
            }
        ),
        encoding="utf-8",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = ExperimentRegistry(repository)
        registry.insert_experiment(
            ExperimentSpec(
                "research-cli",
                datetime(2025, 1, 1, tzinfo=UTC),
                ("run-1",),
                "code",
                ("config",),
                ("data",),
                ("calendar",),
                "universe",
                WalkForwardSpec(),
                "metrics",
                "similarity",
                7,
            )
        )
        registry.insert_fold(
            WalkForwardFold(
                "fold-1",
                "research-cli",
                0,
                date(2020, 1, 1),
                date(2021, 12, 31),
                date(2022, 1, 10),
                date(2022, 3, 31),
                date(2022, 4, 10),
                date(2022, 6, 30),
            )
        )
    common = ["--database", str(database), "--model-experiment-id", "model-cli"]
    assert main(
        [
            "model",
            "define",
            "--database",
            str(database),
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--dataset",
            str(dataset),
        ]
    ) == 0
    assert main(
        [
            "model",
            "train",
            *common,
            "--config",
            str(config),
            "--dataset",
            str(dataset),
            "--cutoff",
            "2026-01-02T00:00:00Z",
            "--artifacts",
            str(artifacts),
        ]
    ) == 0
    for partition in ("VALIDATION", "TEST"):
        if partition == "TEST":
            with SQLiteRepository(database) as repository:
                repository.migrate()
                model_registry = ModelRegistry(repository)
                frozen_hash = canonical_hash(
                    model_registry.experiment_manifest("model-cli")
                )
            assert main(
                ["model", "freeze", *common, "--manifest-hash", frozen_hash]
            ) == 0
        assert main(
            [
                "model",
                "evaluate",
                *common,
                "--config",
                str(config),
                "--dataset",
                str(dataset),
                "--cutoff",
                "2026-01-02T00:00:00Z",
                "--partition",
                partition,
            ]
        ) == 0
    assert main(["model", "complete", *common]) == 0
    assert main(["model", "verify-artifacts", *common]) == 0
    assert main(["model", "report", *common, "--output", str(report)]) == 0
    assert "RESEARCH_ONLY" in report.read_text(encoding="utf-8")
