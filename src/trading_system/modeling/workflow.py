"""Fold-local Phase 3A fitting and evaluation orchestration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from trading_system.modeling.artifacts import load_artifact, write_artifact
from trading_system.modeling.contracts import ModelPrediction, ModelRow
from trading_system.modeling.engine import (
    FittedBaselines,
    dummy_probabilities,
    fit_baselines,
    predict_probabilities,
)
from trading_system.modeling.metrics import probability_metrics
from trading_system.modeling.registry import ModelRegistry
from trading_system.serialization import deterministic_id


class ModelWorkflow:
    def __init__(self, registry: ModelRegistry, model_experiment_id: str) -> None:
        self.registry = registry
        self.model_experiment_id = model_experiment_id

    def train_fold(
        self,
        fold_id: str,
        rows: tuple[ModelRow, ...],
        targets: tuple[int, ...],
        *,
        numeric_features: tuple[str, ...],
        categorical_features: tuple[str, ...],
        seed: int,
        c_value: float,
        max_iter: int,
        calibration_minimum_class_count: int,
        bootstrap_samples: int,
        artifact_directory: str | Path,
        manifest: dict[str, object],
        known_at: datetime,
    ) -> str:
        fitted = fit_baselines(
            rows,
            targets,
            numeric_features=numeric_features,
            categorical_features=categorical_features,
            seed=seed,
            c_value=c_value,
            max_iter=max_iter,
            calibration_minimum_class_count=calibration_minimum_class_count,
        )
        record = write_artifact(fitted, artifact_directory, manifest)
        self.registry.insert_artifact(
            self.model_experiment_id,
            fold_id,
            "L2_LOGISTIC_REGRESSION",
            record,
            manifest,
        )
        self.registry.insert_metric(
            self.model_experiment_id,
            fold_id,
            "TRAIN",
            "L2_LOGISTIC_REGRESSION",
            known_at,
            probability_metrics(
                targets,
                predict_probabilities(fitted, rows),
                seed=seed,
                bootstrap_samples=bootstrap_samples,
            ),
        )
        self.registry.insert_metric(
            self.model_experiment_id,
            fold_id,
            "TRAIN",
            "DUMMY_PREVALENCE",
            known_at,
            probability_metrics(
                targets,
                dummy_probabilities(fitted, rows),
                seed=seed,
                bootstrap_samples=bootstrap_samples,
            ),
        )
        return record.artifact_id

    def evaluate_fold(
        self,
        fold_id: str,
        partition: str,
        rows: tuple[ModelRow, ...],
        targets: tuple[int, ...],
        *,
        known_at: datetime,
        seed: int,
        bootstrap_samples: int,
    ) -> int:
        record = self.registry.artifact(self.model_experiment_id, fold_id)
        manifest = self.registry.artifact_manifest(record.artifact_id)
        fitted = load_artifact(record, manifest)
        if not isinstance(fitted, FittedBaselines):
            raise ValueError("artifact does not contain Phase 3A fitted baselines")
        probabilities = predict_probabilities(fitted, rows)
        dummy = dummy_probabilities(fitted, rows)
        self.registry.insert_metric(
            self.model_experiment_id,
            fold_id,
            partition,
            "L2_LOGISTIC_REGRESSION",
            known_at,
            probability_metrics(
                targets,
                probabilities,
                seed=seed,
                bootstrap_samples=bootstrap_samples,
            ),
        )
        self.registry.insert_metric(
            self.model_experiment_id,
            fold_id,
            partition,
            "DUMMY_PREVALENCE",
            known_at,
            probability_metrics(
                targets, dummy, seed=seed, bootstrap_samples=bootstrap_samples
            ),
        )
        inserted = 0
        for row, probability in zip(rows, probabilities, strict=True):
            prediction_id = deterministic_id(
                "model_prediction",
                (
                    self.model_experiment_id,
                    record.artifact_id,
                    row.observation_id,
                    partition,
                ),
            )
            inserted += int(
                self.registry.insert_prediction(
                    ModelPrediction(
                        prediction_id,
                        self.model_experiment_id,
                        record.artifact_id,
                        row.observation_id,
                        fold_id,
                        partition,
                        known_at,
                        probability,
                    )
                )
            )
        return inserted
