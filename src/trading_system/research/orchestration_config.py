"""Strict immutable Phase 2B orchestration configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.research.orchestration import ExperimentStage
from trading_system.serialization import canonical_hash


@dataclass(frozen=True, slots=True)
class OrchestrationConfig:
    version: str
    minimum_cohort_sample: int
    symbol_holdout_buckets: int
    config_hash: str


def load_orchestration_config(path: str | Path) -> OrchestrationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "orchestration_version",
        "minimum_cohort_sample",
        "symbol_holdout_buckets",
        "require_freeze_before_test",
        "stages",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 2B configuration keys are invalid")
    sample = raw["minimum_cohort_sample"]
    buckets = raw["symbol_holdout_buckets"]
    if isinstance(sample, bool) or not isinstance(sample, int) or sample <= 0:
        raise ValueError("minimum cohort sample must be positive")
    if isinstance(buckets, bool) or not isinstance(buckets, int) or buckets <= 1:
        raise ValueError("symbol holdout bucket count must exceed one")
    if raw["require_freeze_before_test"] is not True:
        raise ValueError("freeze before test is mandatory")
    if raw["stages"] != [stage.value for stage in ExperimentStage]:
        raise ValueError("experiment stages are invalid")
    version = raw["orchestration_version"]
    if not isinstance(version, str) or not version:
        raise ValueError("orchestration version is required")
    return OrchestrationConfig(version, sample, buckets, canonical_hash(raw))
