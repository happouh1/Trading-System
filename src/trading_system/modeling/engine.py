"""Fixed deterministic dummy and L2-logistic Phase 3A baselines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.calibration import CalibratedClassifierCV  # type: ignore[import-untyped]
from sklearn.compose import ColumnTransformer  # type: ignore[import-untyped]
from sklearn.dummy import DummyClassifier  # type: ignore[import-untyped]
from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # type: ignore[import-untyped]

from trading_system.modeling.contracts import ModelRow


@dataclass(frozen=True, slots=True)
class FittedBaselines:
    dummy: Any
    logistic: Any
    calibrated: bool
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]


def _matrix(
    rows: tuple[ModelRow, ...],
    numeric: tuple[str, ...],
    categorical: tuple[str, ...],
) -> np.ndarray[Any, np.dtype[np.object_]]:
    return np.asarray(
        [
            [
                *(
                    np.nan if row.features.get(name) is None else row.features.get(name)
                    for name in numeric
                ),
                *(
                    np.nan if row.features.get(name) is None else row.features.get(name)
                    for name in categorical
                ),
            ]
            for row in rows
        ],
        dtype=object,
    )


def fit_baselines(
    rows: tuple[ModelRow, ...],
    targets: tuple[int, ...],
    *,
    numeric_features: tuple[str, ...],
    categorical_features: tuple[str, ...],
    seed: int,
    c_value: float = 1.0,
    max_iter: int = 2000,
    calibration_minimum_class_count: int = 3,
) -> FittedBaselines:
    if len(rows) != len(targets) or not rows:
        raise ValueError("nonempty rows and matching targets are required")
    if set(targets) != {0, 1}:
        raise ValueError("training requires both target classes")
    matrix = _matrix(rows, numeric_features, categorical_features)
    numeric_indices = list(range(len(numeric_features)))
    categorical_indices = list(range(len(numeric_features), matrix.shape[1]))
    numeric_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocess = ColumnTransformer(
        [
            ("numeric", numeric_pipeline, numeric_indices),
            ("categorical", categorical_pipeline, categorical_indices),
        ]
    )
    estimator = Pipeline(
        [
            ("preprocess", preprocess),
            (
                "estimator",
                LogisticRegression(
                    C=c_value,
                    penalty="l2",
                    solver="liblinear",
                    class_weight="balanced",
                    max_iter=max_iter,
                    random_state=seed,
                ),
            ),
        ]
    )
    minimum_class_count = min(targets.count(0), targets.count(1))
    calibrated = minimum_class_count >= calibration_minimum_class_count
    logistic: Any
    if calibrated:
        logistic = CalibratedClassifierCV(estimator, method="sigmoid", cv=3, n_jobs=1)
    else:
        logistic = estimator
    dummy = DummyClassifier(strategy="prior", random_state=seed)
    dummy.fit(matrix, targets)
    logistic.fit(matrix, targets)
    return FittedBaselines(
        dummy, logistic, calibrated, numeric_features, categorical_features
    )


def predict_probabilities(model: FittedBaselines, rows: tuple[ModelRow, ...]) -> tuple[float, ...]:
    matrix = _matrix(rows, model.numeric_features, model.categorical_features)
    values = model.logistic.predict_proba(matrix)[:, 1]
    return tuple(float(value) for value in values)


def dummy_probabilities(model: FittedBaselines, rows: tuple[ModelRow, ...]) -> tuple[float, ...]:
    matrix = _matrix(rows, model.numeric_features, model.categorical_features)
    values = model.dummy.predict_proba(matrix)[:, 1]
    return tuple(float(value) for value in values)
