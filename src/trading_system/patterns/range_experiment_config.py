"""Strict preregistration configuration for Phase 7C range experiments."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.research import WalkForwardSpec
from trading_system.serialization import canonical_hash


class RangeExperimentConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeExperimentConfig:
    values: Mapping[str, object]
    config_hash: str
    folds: WalkForwardSpec
    minimum_observations: int
    minimum_clusters: int
    familywise_alpha: Decimal
    bootstrap_samples: int
    seed: int


def _integer(section: Mapping[str, object], key: str, *, minimum: int) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RangeExperimentConfigError(f"{key} must be an integer >= {minimum}")
    return value


def load_range_experiment_config(path: str | Path) -> RangeExperimentConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "experiment_version", "walk_forward", "evidence_gates", "statistics", "authority"
    }:
        raise RangeExperimentConfigError("range experiment top-level keys are invalid")
    if raw["experiment_version"] != "7C.1.0":
        raise RangeExperimentConfigError("experiment_version must be 7C.1.0")
    walk = raw["walk_forward"]
    gates = raw["evidence_gates"]
    stats = raw["statistics"]
    authority = raw["authority"]
    if not all(isinstance(item, dict) for item in (walk, gates, stats, authority)):
        raise RangeExperimentConfigError("configuration sections must be objects")
    assert isinstance(walk, dict) and isinstance(gates, dict)
    assert isinstance(stats, dict) and isinstance(authority, dict)
    if set(walk) != {
        "minimum_train_sessions", "validation_sessions", "test_sessions",
        "step_sessions", "embargo_sessions",
    }:
        raise RangeExperimentConfigError("walk_forward keys are invalid")
    folds = WalkForwardSpec(
        _integer(walk, "minimum_train_sessions", minimum=1),
        _integer(walk, "validation_sessions", minimum=1),
        _integer(walk, "test_sessions", minimum=1),
        _integer(walk, "step_sessions", minimum=1),
        _integer(walk, "embargo_sessions", minimum=0),
    )
    if set(gates) != {
        "minimum_observations_per_cohort", "minimum_independent_box_clusters", "cluster_key"
    } or gates["cluster_key"] != "BOX_ID":
        raise RangeExperimentConfigError("evidence_gates are invalid")
    if set(stats) != {
        "familywise_alpha", "multiple_testing_correction", "bootstrap_samples", "seed",
        "transaction_cost_model",
    }:
        raise RangeExperimentConfigError("statistics keys are invalid")
    try:
        alpha = Decimal(str(stats["familywise_alpha"]))
    except ArithmeticError as exc:
        raise RangeExperimentConfigError("familywise_alpha must be numeric") from exc
    if not Decimal(0) < alpha < Decimal(1):
        raise RangeExperimentConfigError("familywise_alpha must be between zero and one")
    if stats["multiple_testing_correction"] != "HOLM":
        raise RangeExperimentConfigError("Phase 7C correction must be HOLM")
    if stats["transaction_cost_model"] != "NOT_APPLICABLE_DIRECTION_NEUTRAL":
        raise RangeExperimentConfigError("direction-neutral outcomes cannot claim a cost model")
    expected_authority = {
        "preregistration_only": True,
        "efficacy_claims_enabled": False,
        "parameter_selection_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }
    if authority != expected_authority:
        raise RangeExperimentConfigError("Phase 7C authority must remain preregistration-only")
    frozen = MappingProxyType(
        {
            key: MappingProxyType(value) if isinstance(value, dict) else value
            for key, value in raw.items()
        }
    )
    return RangeExperimentConfig(
        frozen,
        canonical_hash(raw),
        folds,
        _integer(gates, "minimum_observations_per_cohort", minimum=1),
        _integer(gates, "minimum_independent_box_clusters", minimum=1),
        alpha,
        _integer(stats, "bootstrap_samples", minimum=1),
        _integer(stats, "seed", minimum=0),
    )
