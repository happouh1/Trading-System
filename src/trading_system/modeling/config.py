"""Strict versioned Phase 3A model configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


@dataclass(frozen=True, slots=True)
class ModelConfig:
    values: Mapping[str, object]
    config_hash: str


def load_model_config(path: str | Path) -> ModelConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "model_version",
        "target",
        "numeric_features",
        "categorical_features",
        "estimator",
        "calibration",
        "diagnostic_thresholds",
        "bootstrap_samples",
        "minimum_breakdown_sample",
        "determinism",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 3A configuration keys are invalid")
    numeric = raw["numeric_features"]
    categorical = raw["categorical_features"]
    if not isinstance(numeric, list) or not isinstance(categorical, list):
        raise ValueError("model features must be lists")
    if not numeric or not all(isinstance(item, str) for item in numeric):
        raise ValueError("numeric features must be nonempty strings")
    if not categorical or not all(isinstance(item, str) for item in categorical):
        raise ValueError("categorical features must be nonempty strings")
    if set(numeric) & set(categorical):
        raise ValueError("numeric and categorical features must be disjoint")
    estimator = raw["estimator"]
    if (
        not isinstance(estimator, dict)
        or set(estimator) != {"kind", "c", "max_iter", "class_weight", "solver"}
        or estimator.get("kind") != "L2_LOGISTIC_REGRESSION"
        or estimator.get("class_weight") != "balanced"
        or estimator.get("solver") != "liblinear"
    ):
        raise ValueError("unsupported Phase 3A estimator")
    c_value = estimator["c"]
    max_iter = estimator["max_iter"]
    if isinstance(c_value, bool) or not isinstance(c_value, (int, float)) or c_value <= 0:
        raise ValueError("logistic C must be positive")
    if isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter <= 0:
        raise ValueError("logistic max_iter must be positive")
    calibration = raw["calibration"]
    if (
        not isinstance(calibration, dict)
        or set(calibration) != {"method", "minimum_class_count"}
        or calibration.get("method") != "sigmoid"
    ):
        raise ValueError("unsupported calibration configuration")
    minimum_class_count = calibration["minimum_class_count"]
    if (
        isinstance(minimum_class_count, bool)
        or not isinstance(minimum_class_count, int)
        or minimum_class_count < 2
    ):
        raise ValueError("calibration minimum class count must be at least two")
    determinism = raw["determinism"]
    if not isinstance(determinism, dict) or determinism.get("jobs") != 1:
        raise ValueError("Phase 3A fitting must be single-process")
    thresholds = raw["diagnostic_thresholds"]
    if not isinstance(thresholds, list) or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1
        for value in thresholds
    ):
        raise ValueError("diagnostic thresholds must be probabilities")
    bootstrap_samples = raw["bootstrap_samples"]
    if (
        isinstance(bootstrap_samples, bool)
        or not isinstance(bootstrap_samples, int)
        or bootstrap_samples <= 0
    ):
        raise ValueError("bootstrap sample count must be positive")
    return ModelConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
