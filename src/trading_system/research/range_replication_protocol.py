"""Prospective-only Phase 8F independent-replication preregistration contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

from trading_system.research.range_confirmatory_export_registry import (
    RangeConfirmatoryExportStatus,
)
from trading_system.serialization import canonical_hash, deterministic_id

_DISCLOSURES = (
    "SOURCE_RESULTS_ALREADY_EXIST_AND_MAY_HAVE_BEEN_INSPECTED",
    "VALID_ONLY_FOR_NEW_INDEPENDENT_REPLICATION",
    "LOCAL_DECLARED_AT_IS_NOT_A_TRUSTED_TIMESTAMP",
    "NO_ANALYSIS_EFFICACY_SELECTION_OR_PRODUCTION_AUTHORITY",
)
_MANIFEST_KEYS = {
    "protocol_name",
    "future_dataset_id",
    "declared_at",
    "data_freeze_rule",
    "estimator_spec",
    "interval_spec",
    "economic_threshold_spec",
    "transaction_cost_spec",
    "capacity_spec",
    "pooling_spec",
    "dependence_diagnostics_spec",
    "replication_acceptance_spec",
    "point_in_time_universe_spec",
    "review_authority_reference",
}


class RangeReplicationProtocolConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeReplicationProtocolConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeReplicationProtocol:
    protocol_id: str
    source_export_id: str
    source_report_id: str
    protocol_name: str
    future_dataset_id: str
    declared_at: str
    data_freeze_rule: str
    estimator_spec: str
    interval_spec: str
    economic_threshold_spec: str
    transaction_cost_spec: str
    capacity_spec: str
    pooling_spec: str
    dependence_diagnostics_spec: str
    replication_acceptance_spec: str
    point_in_time_universe_spec: str
    review_authority_reference: str
    definition_hash: str
    protocol_config_hash: str
    disclosures: tuple[str, ...]
    protocol_version: str = "8F.1.0"
    prospective_replication_only: bool = True
    source_results_already_exist: bool = True
    analysis_performed: bool = False
    efficacy_claimed: bool = False
    parameter_selection_performed: bool = False
    approval_granted: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        required = (
            self.protocol_id,
            self.source_export_id,
            self.source_report_id,
            self.protocol_name,
            self.future_dataset_id,
            self.declared_at,
            self.data_freeze_rule,
            self.estimator_spec,
            self.interval_spec,
            self.economic_threshold_spec,
            self.transaction_cost_spec,
            self.capacity_spec,
            self.pooling_spec,
            self.dependence_diagnostics_spec,
            self.replication_acceptance_spec,
            self.point_in_time_universe_spec,
            self.review_authority_reference,
        )
        if (
            not all(required)
            or not self.definition_hash.startswith("sha256:")
            or not self.protocol_config_hash.startswith("sha256:")
            or self.disclosures != _DISCLOSURES
            or self.protocol_version != "8F.1.0"
            or not self.prospective_replication_only
            or not self.source_results_already_exist
            or any(
                (
                    self.analysis_performed,
                    self.efficacy_claimed,
                    self.parameter_selection_performed,
                    self.approval_granted,
                    self.network_used,
                    self.broker_write_performed,
                    self.production_authority,
                )
            )
        ):
            raise ValueError("invalid Phase 8F replication protocol")


def load_range_replication_protocol_config(
    path: str | Path,
) -> RangeReplicationProtocolConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "protocol_version",
        "source",
        "registration_mode",
        "hypothesis_scope",
        "required_disclosures",
        "authority",
    }:
        raise RangeReplicationProtocolConfigError(
            "Phase 8F configuration keys are invalid"
        )
    if (
        raw["protocol_version"] != "8F.1.0"
        or raw["source"] != "VERIFIED_PHASE8D_EXPORT"
        or raw["registration_mode"]
        != "PROSPECTIVE_INDEPENDENT_REPLICATION_ONLY"
        or raw["hypothesis_scope"] != "EXACT_SOURCE_REPORT_FAMILY"
        or raw["required_disclosures"] != list(_DISCLOSURES)
    ):
        raise RangeReplicationProtocolConfigError(
            "Phase 8F protocol policy is invalid"
        )
    authority = raw["authority"]
    expected_authority = {
        "analysis_enabled",
        "effect_size_calculation_enabled",
        "efficacy_claims_enabled",
        "parameter_selection_enabled",
        "ranking_enabled",
        "approval_enabled",
        "network_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    }
    if not isinstance(authority, dict) or set(authority) != expected_authority or any(
        value is not False for value in authority.values()
    ):
        raise RangeReplicationProtocolConfigError(
            "Phase 8F authority must remain preregistration-only"
        )
    frozen = {
        key: tuple(value) if isinstance(value, list)
        else MappingProxyType(dict(value)) if isinstance(value, dict)
        else value
        for key, value in raw.items()
    }
    return RangeReplicationProtocolConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


def _canonical_declared_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("declared_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("declared_at must be UTC")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def build_range_replication_protocol(
    config: RangeReplicationProtocolConfig,
    *,
    source: RangeConfirmatoryExportStatus,
    manifest: Mapping[str, object],
) -> RangeReplicationProtocol:
    if not source.verified or source.export_version != "8D.1.0":
        raise ValueError("Phase 8F requires a verified Phase 8D source")
    if set(manifest) != _MANIFEST_KEYS:
        raise ValueError("Phase 8F manifest keys are invalid")
    if not all(isinstance(manifest[key], str) and str(manifest[key]).strip() for key in manifest):
        raise ValueError("Phase 8F manifest values must be nonempty strings")
    values = {key: str(manifest[key]).strip() for key in sorted(_MANIFEST_KEYS)}
    values["declared_at"] = _canonical_declared_at(values["declared_at"])
    definition_hash = canonical_hash(values)
    identity = (
        source.export_id,
        source.report_id,
        values,
        definition_hash,
        config.config_hash,
        "8F.1.0",
    )
    return RangeReplicationProtocol(
        deterministic_id("range_replication_protocol", identity),
        source.export_id,
        source.report_id,
        values["protocol_name"],
        values["future_dataset_id"],
        values["declared_at"],
        values["data_freeze_rule"],
        values["estimator_spec"],
        values["interval_spec"],
        values["economic_threshold_spec"],
        values["transaction_cost_spec"],
        values["capacity_spec"],
        values["pooling_spec"],
        values["dependence_diagnostics_spec"],
        values["replication_acceptance_spec"],
        values["point_in_time_universe_spec"],
        values["review_authority_reference"],
        definition_hash,
        config.config_hash,
        _DISCLOSURES,
    )
