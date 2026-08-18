"""Strict immutable Phase 2A research configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.research.contracts import WalkForwardSpec
from trading_system.serialization import canonical_hash


class ResearchConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResearchConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        section = self.values.get(name)
        if not isinstance(section, Mapping):
            raise ResearchConfigError(f"{name} must be an object")
        return section


def load_research_config(path: str | Path) -> ResearchConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ResearchConfigError("research config must be an object")
    expected = {
        "research_version",
        "folds",
        "statistics",
        "calibration",
        "similarity",
        "determinism",
    }
    if set(raw) != expected:
        raise ResearchConfigError("research config top-level keys are invalid")
    folds = raw["folds"]
    if not isinstance(folds, dict):
        raise ResearchConfigError("folds must be an object")
    fold_keys = {
        "minimum_train_sessions",
        "validation_sessions",
        "test_sessions",
        "step_sessions",
        "embargo_sessions",
    }
    if set(folds) != fold_keys or not all(
        isinstance(folds[key], int) and not isinstance(folds[key], bool)
        for key in fold_keys
    ):
        raise ResearchConfigError("fold configuration is invalid")
    WalkForwardSpec(
        minimum_train_sessions=folds["minimum_train_sessions"],
        validation_sessions=folds["validation_sessions"],
        test_sessions=folds["test_sessions"],
        step_sessions=folds["step_sessions"],
        embargo_sessions=folds["embargo_sessions"],
    )
    similarity = raw["similarity"]
    if not isinstance(similarity, dict) or set(similarity) != {
        "distance",
        "minimum_coverage",
        "features",
    }:
        raise ResearchConfigError("similarity configuration is invalid")
    if similarity["distance"] != "weighted_manhattan_zscore":
        raise ResearchConfigError("unsupported similarity distance")
    coverage = similarity["minimum_coverage"]
    features = similarity["features"]
    if (
        not isinstance(coverage, (int, float))
        or isinstance(coverage, bool)
        or not 0 <= coverage <= 1
    ):
        raise ResearchConfigError("minimum coverage must be in [0,1]")
    if not isinstance(features, dict) or not features:
        raise ResearchConfigError("similarity features are required")
    if any(
        not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0
        for value in features.values()
    ):
        raise ResearchConfigError("similarity weights must be positive numbers")
    return ResearchConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
