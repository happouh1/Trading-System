"""Phase 8I provider-neutral, point-in-time replication-data contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, deterministic_id


class RangeReplicationDataConfigError(ValueError):
    pass


class InstrumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELISTED = "DELISTED"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True, slots=True)
class RangeReplicationDataConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ProviderRevisionManifest:
    manifest_id: str
    provider_id: str
    dataset_revision: str
    corporate_action_revision: str
    calendar_version: str
    adjustment_policy: str
    coverage_start: datetime
    coverage_end: datetime
    known_at: datetime
    content_hash: str
    manifest_signature_id: str | None
    data_boundary_version: str = "8I.1.0"
    externally_attested: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        timestamps = (self.coverage_start, self.coverage_end, self.known_at)
        if (
            not all((self.manifest_id, self.provider_id, self.dataset_revision))
            or not all((self.corporate_action_revision, self.calendar_version))
            or self.adjustment_policy not in {"split_adjusted", "raw_and_split_adjusted"}
            or any(not _is_utc(value) for value in timestamps)
            or self.coverage_start >= self.coverage_end
            or self.known_at < self.coverage_end
            or not _is_hash(self.content_hash)
            or self.data_boundary_version != "8I.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8I provider revision manifest")
        if self.externally_attested != (self.manifest_signature_id is not None):
            raise ValueError("Phase 8I attestation and signature identity must agree")


@dataclass(frozen=True, slots=True)
class PointInTimeMembership:
    instrument_id: str
    symbol: str
    exchange: str
    effective_from: datetime
    effective_to: datetime | None
    status: InstrumentStatus
    membership_source_hash: str

    def __post_init__(self) -> None:
        if (
            not self.instrument_id
            or not self.symbol
            or self.symbol != self.symbol.upper()
            or not self.exchange
            or not _is_utc(self.effective_from)
            or (self.effective_to is not None and not _is_utc(self.effective_to))
            or (self.effective_to is not None and self.effective_to <= self.effective_from)
            or not _is_hash(self.membership_source_hash)
        ):
            raise ValueError("invalid Phase 8I point-in-time membership")

    def active_at(self, as_of: datetime) -> bool:
        _require_utc(as_of)
        return self.effective_from <= as_of and (
            self.effective_to is None or as_of < self.effective_to
        )


@dataclass(frozen=True, slots=True)
class PointInTimeUniverseSnapshot:
    snapshot_id: str
    universe_name: str
    provider_manifest_id: str
    as_of: datetime
    known_at: datetime
    memberships: tuple[PointInTimeMembership, ...]
    content_hash: str
    data_boundary_version: str = "8I.1.0"
    survivorship_safe_claimed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        identities = tuple(item.instrument_id for item in self.memberships)
        if (
            not all((self.snapshot_id, self.universe_name, self.provider_manifest_id))
            or not _is_utc(self.as_of)
            or not _is_utc(self.known_at)
            or self.known_at < self.as_of
            or not self.memberships
            or identities != tuple(sorted(identities))
            or len(identities) != len(set(identities))
            or any(not item.active_at(self.as_of) for item in self.memberships)
            or not _is_hash(self.content_hash)
            or self.data_boundary_version != "8I.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8I universe snapshot")


@dataclass(frozen=True, slots=True)
class ReplicationDataBinding:
    binding_id: str
    collection_id: str
    provider_manifest_id: str
    universe_snapshot_id: str
    bound_at: datetime
    binding_hash: str
    data_config_hash: str
    data_boundary_version: str = "8I.1.0"
    real_data_ready: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.binding_id, self.collection_id, self.provider_manifest_id))
            or not self.universe_snapshot_id
            or not _is_utc(self.bound_at)
            or not _is_hash(self.binding_hash)
            or not _is_hash(self.data_config_hash)
            or self.data_boundary_version != "8I.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8I data binding")


def load_range_replication_data_config(path: str | Path) -> RangeReplicationDataConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "data_boundary_version",
        "mode",
        "requirements",
        "authority",
    }:
        raise RangeReplicationDataConfigError("Phase 8I configuration keys are invalid")
    expected_requirements = {
        "point_in_time_membership": True,
        "immutable_provider_revision": True,
        "corporate_action_revision": True,
        "causal_known_at": True,
        "signed_manifest_required_for_real_use": True,
    }
    if (
        raw["data_boundary_version"] != "8I.1.0"
        or raw["mode"] != "PROVIDER_NEUTRAL_ATTESTED_MANIFEST"
        or raw["requirements"] != expected_requirements
    ):
        raise RangeReplicationDataConfigError("Phase 8I data policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "provider_selected",
        "network_ingestion_enabled",
        "real_dataset_approved",
        "analysis_enabled",
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
        raise RangeReplicationDataConfigError("Phase 8I authority must remain disabled")
    frozen = {key: _freeze_value(value) for key, value in raw.items()}
    return RangeReplicationDataConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_provider_manifest(
    *,
    provider_id: str,
    dataset_revision: str,
    corporate_action_revision: str,
    calendar_version: str,
    adjustment_policy: str,
    coverage_start: datetime,
    coverage_end: datetime,
    known_at: datetime,
    content_hash: str,
    manifest_signature_id: str | None = None,
) -> ProviderRevisionManifest:
    for timestamp in (coverage_start, coverage_end, known_at):
        _require_utc(timestamp)
    core = {
        "provider_id": provider_id,
        "dataset_revision": dataset_revision,
        "corporate_action_revision": corporate_action_revision,
        "calendar_version": calendar_version,
        "adjustment_policy": adjustment_policy,
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "known_at": known_at,
        "content_hash": content_hash,
        "manifest_signature_id": manifest_signature_id,
        "data_boundary_version": "8I.1.0",
    }
    return ProviderRevisionManifest(
        deterministic_id("replication_provider_manifest", core),
        provider_id,
        dataset_revision,
        corporate_action_revision,
        calendar_version,
        adjustment_policy,
        coverage_start.astimezone(UTC),
        coverage_end.astimezone(UTC),
        known_at.astimezone(UTC),
        content_hash,
        manifest_signature_id,
        externally_attested=manifest_signature_id is not None,
    )


def build_universe_snapshot(
    *,
    universe_name: str,
    provider_manifest_id: str,
    as_of: datetime,
    known_at: datetime,
    memberships: Sequence[PointInTimeMembership],
) -> PointInTimeUniverseSnapshot:
    _require_utc(as_of)
    _require_utc(known_at)
    ordered = tuple(sorted(memberships, key=lambda item: item.instrument_id))
    core = {
        "universe_name": universe_name,
        "provider_manifest_id": provider_manifest_id,
        "as_of": as_of,
        "known_at": known_at,
        "memberships": ordered,
        "data_boundary_version": "8I.1.0",
    }
    content_hash = canonical_hash(core)
    return PointInTimeUniverseSnapshot(
        deterministic_id("replication_universe_snapshot", core),
        universe_name,
        provider_manifest_id,
        as_of.astimezone(UTC),
        known_at.astimezone(UTC),
        ordered,
        content_hash,
    )


def _is_hash(value: str) -> bool:
    return value.startswith("sha256:") and len(value) > len("sha256:")


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


def _require_utc(value: datetime) -> None:
    if not _is_utc(value):
        raise ValueError("Phase 8I timestamps must be UTC")


def _freeze_value(value: object) -> object:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise RangeReplicationDataConfigError("Phase 8I config keys must be strings")
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value
