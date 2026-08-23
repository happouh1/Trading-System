"""Immutable Phase 3A model research contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class ModelStage(StrEnum):
    DEFINED = "DEFINED"
    TRAINED = "TRAINED"
    VALIDATION_EVALUATED = "VALIDATION_EVALUATED"
    FROZEN = "FROZEN"
    TEST_EVALUATED = "TEST_EVALUATED"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class ModelExperiment:
    model_experiment_id: str
    research_experiment_id: str
    created_at: datetime
    dataset_hash: str
    feature_schema_hash: str
    target_version: str
    estimator_version: str
    config_hash: str
    code_version: str
    dependency_versions: Mapping[str, str]
    seed: int

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("model experiment time must be timezone-aware")
        object.__setattr__(
            self, "dependency_versions", MappingProxyType(dict(self.dependency_versions))
        )

    @property
    def payload_hash(self) -> str:
        return canonical_hash(self)


@dataclass(frozen=True, slots=True)
class ModelRow:
    row_id: str
    observation_id: str
    fold_id: str
    partition: str
    label_available_at: datetime
    outcome_label: str
    features: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.label_available_at.tzinfo is None or self.label_available_at.utcoffset() is None:
            raise ValueError("label availability must be timezone-aware")
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    prediction_id: str
    model_experiment_id: str
    artifact_id: str
    observation_id: str
    fold_id: str
    partition: str
    known_at: datetime
    probability: float

    def __post_init__(self) -> None:
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("prediction time must be timezone-aware")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be in [0,1]")
