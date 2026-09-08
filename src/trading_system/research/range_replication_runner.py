"""Phase 8K one-shot offline replication runner with no authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.research.range_replication_collection import (
    RangeReplicationFreezeManifest,
)
from trading_system.research.range_replication_statistics import (
    RangeReplicationHypothesis,
    RangeReplicationResult,
    RangeReplicationStatisticsConfig,
    evaluate_replication_family,
)
from trading_system.serialization import canonical_hash, deterministic_id


class RangeReplicationRunnerConfigError(ValueError):
    pass


class ReplicationRunState(StrEnum):
    SEALED = "SEALED"


@dataclass(frozen=True, slots=True)
class RangeReplicationRunnerConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeReplicationRun:
    run_id: str
    freeze_id: str
    collection_id: str
    executed_at: datetime
    family_input_hash: str
    result_root_hash: str
    result_count: int
    state: ReplicationRunState
    runner_config_hash: str
    statistics_config_hash: str
    runner_version: str = "8K.1.0"
    test_only: bool = True
    efficacy_claimed: bool = False
    parameter_selection_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.run_id, self.freeze_id, self.collection_id))
            or self.executed_at.tzinfo is None
            or self.executed_at.utcoffset() != UTC.utcoffset(self.executed_at)
            or self.result_count <= 0
            or any(
                not value.startswith("sha256:")
                for value in (
                    self.family_input_hash,
                    self.result_root_hash,
                    self.runner_config_hash,
                    self.statistics_config_hash,
                )
            )
            or self.runner_version != "8K.1.0"
            or not self.test_only
            or self.efficacy_claimed
            or self.parameter_selection_performed
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8K run")


def load_range_replication_runner_config(path: str | Path) -> RangeReplicationRunnerConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"runner_version", "mode", "method", "prerequisites", "authority"}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RangeReplicationRunnerConfigError("Phase 8K configuration keys are invalid")
    if raw["runner_version"] != "8K.1.0" or raw["mode"] != (
        "OFFLINE_TEST_ONLY_REPLICATION_REHEARSAL"
    ):
        raise RangeReplicationRunnerConfigError("Phase 8K mode is invalid")
    if raw["method"] != {
        "statistics_kernel": "PHASE8G_EXACT_UNMODIFIED",
        "input_order": "CANONICAL_HYPOTHESIS_ID",
        "analyses_per_freeze": 1,
        "persist_raw_outcomes": False,
    }:
        raise RangeReplicationRunnerConfigError("Phase 8K method is invalid")
    prerequisites = raw["prerequisites"]
    if not isinstance(prerequisites, dict) or set(prerequisites) != {
        "frozen_collection_required",
        "complete_family_required",
        "explicit_thresholds_required",
        "independent_real_release_required_for_real_claims",
    } or any(value is not True for value in prerequisites.values()):
        raise RangeReplicationRunnerConfigError("Phase 8K prerequisites must remain strict")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "real_dataset_access_enabled",
        "efficacy_claims_enabled",
        "parameter_selection_enabled",
        "ranking_enabled",
        "alerts_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise RangeReplicationRunnerConfigError("Phase 8K authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeReplicationRunnerConfig(MappingProxyType(frozen), canonical_hash(raw))


def run_replication_rehearsal(
    config: RangeReplicationRunnerConfig,
    statistics_config: RangeReplicationStatisticsConfig,
    *,
    freeze: RangeReplicationFreezeManifest,
    hypotheses: tuple[RangeReplicationHypothesis, ...],
    executed_at: datetime,
    familywise_alpha: Decimal,
    economic_threshold_net_r: Decimal,
    minimum_total_clusters: int,
    minimum_nonzero_clusters: int,
) -> tuple[RangeReplicationRun, tuple[RangeReplicationResult, ...]]:
    if not freeze.test_only or freeze.released_for_analysis or freeze.production_authority:
        raise ValueError("Phase 8K reference accepts only unreleased test-only freezes")
    if executed_at.tzinfo is None or executed_at.utcoffset() != UTC.utcoffset(executed_at):
        raise ValueError("Phase 8K execution time must be UTC")
    if executed_at < freeze.frozen_at:
        raise ValueError("Phase 8K cannot execute before the collection freeze")
    ordered = tuple(sorted(hypotheses, key=lambda item: item.hypothesis_id))
    family_input = {
        "freeze_id": freeze.freeze_id,
        "manifest_hash": freeze.manifest_hash,
        "hypotheses": ordered,
        "familywise_alpha": familywise_alpha,
        "economic_threshold_net_r": economic_threshold_net_r,
        "minimum_total_clusters": minimum_total_clusters,
        "minimum_nonzero_clusters": minimum_nonzero_clusters,
    }
    results = evaluate_replication_family(
        statistics_config,
        hypotheses=ordered,
        familywise_alpha=familywise_alpha,
        economic_threshold_net_r=economic_threshold_net_r,
        minimum_total_clusters=minimum_total_clusters,
        minimum_nonzero_clusters=minimum_nonzero_clusters,
    )
    family_hash = canonical_hash(family_input)
    result_root = canonical_hash(tuple(canonical_hash(result) for result in results))
    identity = (
        freeze.freeze_id,
        executed_at,
        family_hash,
        result_root,
        config.config_hash,
        statistics_config.config_hash,
    )
    run = RangeReplicationRun(
        deterministic_id("range_replication_run", identity),
        freeze.freeze_id,
        freeze.collection_id,
        executed_at,
        family_hash,
        result_root,
        len(results),
        ReplicationRunState.SEALED,
        config.config_hash,
        statistics_config.config_hash,
    )
    return run, results
