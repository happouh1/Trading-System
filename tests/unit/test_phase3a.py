from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.modeling.artifacts import load_artifact, write_artifact
from trading_system.modeling.config import load_model_config
from trading_system.modeling.contracts import ModelRow
from trading_system.modeling.dataset import prepare_rows
from trading_system.modeling.engine import fit_baselines, predict_probabilities
from trading_system.modeling.metrics import probability_metrics

ROOT = Path(__file__).parents[2]


def row(
    row_id: str,
    label: str,
    x: float | None,
    pattern: str = "BREAKOUT",
) -> ModelRow:
    return ModelRow(
        row_id,
        f"observation-{row_id}",
        "fold-1",
        "TRAIN",
        datetime(2026, 1, 1, tzinfo=UTC),
        label,
        {"trend_score": x, "pattern": pattern},
    )


def test_model_config_is_strict_and_versioned() -> None:
    config = load_model_config(ROOT / "config/model.phase3a.v1.yaml")
    assert config.config_hash.startswith("sha256:")
    assert config.values["model_version"] == "3A.1.0"


def test_dataset_rejects_future_and_forbidden_features() -> None:
    cutoff = datetime(2026, 1, 2, tzinfo=UTC)
    future = ModelRow(
        "future",
        "observation-future",
        "fold-1",
        "TRAIN",
        cutoff + timedelta(days=1),
        "GENERIC_SUCCESS",
        {"trend_score": 50.0, "pattern": "BREAKOUT"},
    )
    prepared = prepare_rows(
        (future,),
        numeric_features=("trend_score",),
        categorical_features=("pattern",),
        positive_labels=("GENERIC_SUCCESS",),
        negative_labels=("GENERIC_FAILURE",),
        cutoff=cutoff,
    )
    assert prepared.excluded == (("future", "LABEL_UNAVAILABLE_AT_CUTOFF"),)
    with pytest.raises(ValueError, match="forbidden"):
        prepare_rows(
            (future,),
            numeric_features=("mfe_r",),
            categorical_features=(),
            positive_labels=("GENERIC_SUCCESS",),
            negative_labels=("GENERIC_FAILURE",),
            cutoff=cutoff,
        )


def test_logistic_fit_is_deterministic_and_handles_missing_and_unseen_category() -> None:
    rows = (
        row("a", "GENERIC_FAILURE", 20.0),
        row("b", "GENERIC_FAILURE", None),
        row("c", "GENERIC_FAILURE", 35.0),
        row("d", "GENERIC_SUCCESS", 65.0),
        row("e", "GENERIC_SUCCESS", 80.0),
        row("f", "GENERIC_SUCCESS", 70.0),
    )
    targets = (0, 0, 0, 1, 1, 1)
    first = fit_baselines(
        rows,
        targets,
        numeric_features=("trend_score",),
        categorical_features=("pattern",),
        seed=7,
    )
    second = fit_baselines(
        rows,
        targets,
        numeric_features=("trend_score",),
        categorical_features=("pattern",),
        seed=7,
    )
    unseen = (row("g", "GENERIC_SUCCESS", None, "RECLAIM"),)
    assert predict_probabilities(first, unseen) == predict_probabilities(second, unseen)


def test_single_class_training_is_rejected() -> None:
    with pytest.raises(ValueError, match="both target classes"):
        fit_baselines(
            (row("a", "GENERIC_SUCCESS", 50.0),),
            (1,),
            numeric_features=("trend_score",),
            categorical_features=("pattern",),
            seed=7,
        )


def test_artifact_hash_tampering_is_rejected(tmp_path: Path) -> None:
    record = write_artifact({"coefficient": 1}, tmp_path, {"version": "1"})
    assert load_artifact(record, {"version": "1"}) == {"coefficient": 1}
    with pytest.raises(ValueError, match="manifest hash"):
        load_artifact(record, {"version": "2"})
    Path(record.path).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="content hash"):
        load_artifact(record, {"version": "1"})


def test_probability_metrics_support_single_class_evaluation() -> None:
    metrics = probability_metrics((1, 1), (0.7, 0.8))
    assert metrics.roc_auc is None
    assert metrics.count == 2
    assert metrics.brier_score > 0
