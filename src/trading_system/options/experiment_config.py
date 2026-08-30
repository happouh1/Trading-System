"""Strict Phase 4D chronological options-experiment configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class OptionsExperimentConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OptionsExperimentConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise OptionsExperimentConfigError(f"{name} must be an object")
        return value

    def integer(self, section: str, name: str) -> int:
        value = self.section(section).get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise OptionsExperimentConfigError(f"{section}.{name} must be an integer")
        return value


def load_options_experiment_config(path: str | Path) -> OptionsExperimentConfig:
    raw: object = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "experiment_version",
        "authority",
        "folds",
        "evaluation",
    }:
        raise OptionsExperimentConfigError("Phase 4D configuration keys are invalid")
    authority = raw["authority"]
    expected_authority = {
        "research_only": True,
        "automatic_optimization_enabled": False,
        "options_execution_enabled": False,
        "portfolio_performance_claims_enabled": False,
    }
    if authority != expected_authority:
        raise OptionsExperimentConfigError("Phase 4D authority must remain research-only")
    folds = raw["folds"]
    fold_keys = {
        "minimum_train_sessions",
        "validation_sessions",
        "test_sessions",
        "step_sessions",
        "embargo_sessions",
    }
    if not isinstance(folds, dict) or set(folds) != fold_keys:
        raise OptionsExperimentConfigError("Phase 4D fold configuration is invalid")
    for key in fold_keys:
        value = folds[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise OptionsExperimentConfigError("Phase 4D fold windows must be integers")
        if value < 0 or (key != "embargo_sessions" and value == 0):
            raise OptionsExperimentConfigError("Phase 4D fold windows are invalid")
    evaluation = raw["evaluation"]
    expected_keys = {
        "assignment_timestamp",
        "label_available_timestamp",
        "require_freeze_before_test",
        "minimum_partition_sample",
        "overlapping_cases_policy",
    }
    if not isinstance(evaluation, dict) or set(evaluation) != expected_keys:
        raise OptionsExperimentConfigError("Phase 4D evaluation configuration is invalid")
    minimum = evaluation["minimum_partition_sample"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum <= 0:
        raise OptionsExperimentConfigError("minimum partition sample must be positive")
    expected_evaluation = {
        "assignment_timestamp": "SCREEN_KNOWN_AT",
        "label_available_timestamp": "EXIT_AS_OF",
        "require_freeze_before_test": True,
        "minimum_partition_sample": minimum,
        "overlapping_cases_policy": "CASE_LEVEL_DISCLOSURE_ONLY",
    }
    if evaluation != expected_evaluation:
        raise OptionsExperimentConfigError("Phase 4D causal evaluation policy is locked")
    version = raw["experiment_version"]
    if not isinstance(version, str) or not version:
        raise OptionsExperimentConfigError("experiment version is required")
    return OptionsExperimentConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
