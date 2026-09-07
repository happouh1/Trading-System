"""Test-only Phase 8H prospective replication collection contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class RangeReplicationCollectionConfigError(ValueError):
    pass


class ReplicationCollectionState(StrEnum):
    REGISTERED = "REGISTERED"
    COLLECTING = "COLLECTING"
    COLLECTION_CLOSED = "COLLECTION_CLOSED"
    OUTCOMES_COMPLETE = "OUTCOMES_COMPLETE"
    FROZEN = "FROZEN"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True, slots=True)
class RangeReplicationCollectionConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeReplicationCollection:
    collection_id: str
    protocol_id: str
    dataset_id: str
    registered_at: datetime
    collection_start: datetime
    collection_end: datetime
    state: ReplicationCollectionState
    config_hash: str
    collection_version: str = "8H.1.0"
    test_only: bool = True
    real_blinding_attested: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        timestamps = (self.registered_at, self.collection_start, self.collection_end)
        if (
            not self.collection_id
            or not self.protocol_id
            or not self.dataset_id.startswith("TEST_ONLY_")
            or any(value.tzinfo is None or value.utcoffset() is None for value in timestamps)
            or not self.registered_at < self.collection_start < self.collection_end
            or not self.config_hash.startswith("sha256:")
            or self.collection_version != "8H.1.0"
            or not self.test_only
            or self.real_blinding_attested
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8H collection")


@dataclass(frozen=True, slots=True)
class RangeReplicationPrediction:
    prediction_id: str
    collection_id: str
    hypothesis_id: str
    box_id: str
    symbol: str
    known_at: datetime
    earliest_outcome_at: datetime
    evidence_hash: str
    payload_hash: str
    collection_version: str = "8H.1.0"
    outcome_present: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.prediction_id, self.collection_id, self.hypothesis_id, self.box_id))
            or not self.symbol
            or self.known_at.tzinfo is None
            or self.known_at.utcoffset() is None
            or self.earliest_outcome_at.tzinfo is None
            or self.earliest_outcome_at.utcoffset() is None
            or self.known_at >= self.earliest_outcome_at
            or not self.evidence_hash.startswith("sha256:")
            or not self.payload_hash.startswith("sha256:")
            or self.collection_version != "8H.1.0"
            or self.outcome_present
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8H prediction")


@dataclass(frozen=True, slots=True)
class RangeReplicationOutcome:
    outcome_id: str
    prediction_id: str
    known_at: datetime
    gross_directional_return: Decimal
    costs: tuple[tuple[str, Decimal], ...]
    net_directional_return: Decimal
    capacity_eligible: bool
    source_hash: str
    payload_hash: str
    collection_version: str = "8H.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        cost_names = tuple(name for name, _ in self.costs)
        if (
            not self.outcome_id
            or not self.prediction_id
            or self.known_at.tzinfo is None
            or self.known_at.utcoffset() is None
            or not self.gross_directional_return.is_finite()
            or not self.net_directional_return.is_finite()
            or cost_names != tuple(sorted(cost_names))
            or len(cost_names) != len(set(cost_names))
            or any(not name or not value.is_finite() or value < 0 for name, value in self.costs)
            or self.net_directional_return
            != self.gross_directional_return - sum((value for _, value in self.costs), Decimal(0))
            or not self.source_hash.startswith("sha256:")
            or not self.payload_hash.startswith("sha256:")
            or self.collection_version != "8H.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8H outcome")


@dataclass(frozen=True, slots=True)
class RangeReplicationFreezeManifest:
    freeze_id: str
    collection_id: str
    frozen_at: datetime
    prediction_count: int
    outcome_count: int
    prediction_root_hash: str
    outcome_root_hash: str
    manifest_hash: str
    collection_version: str = "8H.1.0"
    test_only: bool = True
    real_blinding_attested: bool = False
    released_for_analysis: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.freeze_id
            or not self.collection_id
            or self.frozen_at.tzinfo is None
            or self.frozen_at.utcoffset() is None
            or self.prediction_count <= 0
            or self.outcome_count != self.prediction_count
            or any(
                not value.startswith("sha256:")
                for value in (
                    self.prediction_root_hash,
                    self.outcome_root_hash,
                    self.manifest_hash,
                )
            )
            or self.collection_version != "8H.1.0"
            or not self.test_only
            or self.real_blinding_attested
            or self.released_for_analysis
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8H freeze manifest")


def load_range_replication_collection_config(
    path: str | Path,
) -> RangeReplicationCollectionConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "collection_version",
        "mode",
        "source",
        "rules",
        "authority",
    }:
        raise RangeReplicationCollectionConfigError("Phase 8H configuration keys are invalid")
    if (
        raw["collection_version"] != "8H.1.0"
        or raw["mode"] != "OFFLINE_TEST_ONLY_REFERENCE"
        or raw["source"] != "COMPLETE_PHASE8F_PROTOCOL_REQUIRED"
        or raw["rules"]
        != {
            "dataset_id_prefix": "TEST_ONLY_",
            "prediction_before_outcome_availability": True,
            "outcome_after_registered_availability": True,
            "append_only": True,
            "complete_outcomes_before_freeze": True,
            "real_blinding_claimed": False,
        }
    ):
        raise RangeReplicationCollectionConfigError("Phase 8H collection policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "real_collection_enabled",
        "outcome_read_api_enabled",
        "analysis_enabled",
        "efficacy_claims_enabled",
        "parameter_selection_enabled",
        "alerts_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise RangeReplicationCollectionConfigError("Phase 8H authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeReplicationCollectionConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_test_collection(
    config: RangeReplicationCollectionConfig,
    *,
    protocol_id: str,
    dataset_id: str,
    registered_at: datetime,
    collection_start: datetime,
    collection_end: datetime,
) -> RangeReplicationCollection:
    identity = (
        protocol_id,
        dataset_id,
        registered_at,
        collection_start,
        collection_end,
        config.config_hash,
        "8H.1.0",
    )
    return RangeReplicationCollection(
        deterministic_id("range_replication_collection", identity),
        protocol_id,
        dataset_id,
        registered_at.astimezone(UTC),
        collection_start.astimezone(UTC),
        collection_end.astimezone(UTC),
        ReplicationCollectionState.REGISTERED,
        config.config_hash,
    )
