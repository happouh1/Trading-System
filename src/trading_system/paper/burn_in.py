"""Phase 9B deterministic paper burn-in evidence without promotion authority."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from trading_system.paper.operator_control import OperatorHealth, PaperOperatorSnapshot
from trading_system.serialization import canonical_hash, deterministic_id


class PaperBurnInConfigError(ValueError):
    pass


class BurnInState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class PaperBurnInConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class PaperBurnInProtocol:
    protocol_id: str
    session_id: str
    declared_at: datetime
    window_start: datetime
    window_end: datetime
    minimum_observations: int
    maximum_attention_fraction: Decimal
    maximum_incidents: int
    maximum_unmatched_reconciliations: int
    definition_hash: str
    config_hash: str
    burn_in_version: str = "9B.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        timestamps = (self.declared_at, self.window_start, self.window_end)
        if (
            not self.protocol_id
            or not self.session_id
            or any(
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
                for value in timestamps
            )
            or not self.declared_at < self.window_start < self.window_end
            or self.minimum_observations <= 0
            or not Decimal(0) <= self.maximum_attention_fraction <= Decimal(1)
            or self.maximum_incidents < 0
            or self.maximum_unmatched_reconciliations < 0
            or not self.definition_hash.startswith("sha256:")
            or not self.config_hash.startswith("sha256:")
            or self.burn_in_version != "9B.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 9B burn-in protocol")


@dataclass(frozen=True, slots=True)
class PaperBurnInAssessment:
    assessment_id: str
    protocol_id: str
    session_id: str
    evaluated_at: datetime
    state: BurnInState
    observation_count: int
    attention_count: int
    attention_fraction: Decimal
    maximum_incident_count: int
    maximum_unmatched_reconciliation_count: int
    snapshot_root_hash: str
    reason_codes: tuple[str, ...]
    protocol_definition_hash: str
    config_hash: str
    burn_in_version: str = "9B.1.0"
    readiness_claimed: bool = False
    automatic_promotion_performed: bool = False
    broker_write_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.protocol_id, self.session_id))
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() != UTC.utcoffset(self.evaluated_at)
            or self.observation_count < 0
            or not 0 <= self.attention_count <= self.observation_count
            or not Decimal(0) <= self.attention_fraction <= Decimal(1)
            or min(
                self.maximum_incident_count,
                self.maximum_unmatched_reconciliation_count,
            ) < 0
            or self.reason_codes != tuple(sorted(set(self.reason_codes)))
            or any(
                not value.startswith("sha256:")
                for value in (
                    self.snapshot_root_hash,
                    self.protocol_definition_hash,
                    self.config_hash,
                )
            )
            or self.burn_in_version != "9B.1.0"
            or self.readiness_claimed
            or self.automatic_promotion_performed
            or self.broker_write_performed
            or self.production_authority
        ):
            raise ValueError("invalid Phase 9B burn-in assessment")


def load_paper_burn_in_config(path: str | Path) -> PaperBurnInConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "burn_in_version", "mode", "method", "authority"
    }:
        raise PaperBurnInConfigError("Phase 9B configuration keys are invalid")
    if raw["burn_in_version"] != "9B.1.0" or raw["mode"] != (
        "OFFLINE_PAPER_BURN_IN_EVIDENCE"
    ):
        raise PaperBurnInConfigError("Phase 9B mode is invalid")
    if raw["method"] != {
        "threshold_source": "PREREGISTERED_OPERATOR_PROTOCOL",
        "observation_source": "IMMUTABLE_PHASE9A_SNAPSHOTS",
        "attention_measure": "ATTENTION_OR_HALTED_SNAPSHOT_FRACTION",
        "incident_measure": "MAXIMUM_CUMULATIVE_INCIDENT_COUNT",
        "reconciliation_measure": "MAXIMUM_CUMULATIVE_UNMATCHED_COUNT",
        "assessments_per_protocol": 1,
    }:
        raise PaperBurnInConfigError("Phase 9B method is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "default_thresholds_enabled",
        "automatic_pass_promotion_enabled",
        "process_execution_enabled",
        "network_enabled",
        "external_notifications_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise PaperBurnInConfigError("Phase 9B authority must remain disabled")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return PaperBurnInConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_burn_in_protocol(
    config: PaperBurnInConfig,
    *,
    session_id: str,
    declared_at: datetime,
    window_start: datetime,
    window_end: datetime,
    minimum_observations: int,
    maximum_attention_fraction: Decimal,
    maximum_incidents: int,
    maximum_unmatched_reconciliations: int,
) -> PaperBurnInProtocol:
    definition = (
        session_id,
        declared_at,
        window_start,
        window_end,
        minimum_observations,
        maximum_attention_fraction,
        maximum_incidents,
        maximum_unmatched_reconciliations,
        config.config_hash,
        "9B.1.0",
    )
    definition_hash = canonical_hash(definition)
    return PaperBurnInProtocol(
        deterministic_id("paper_burn_in_protocol", definition),
        session_id,
        declared_at,
        window_start,
        window_end,
        minimum_observations,
        maximum_attention_fraction,
        maximum_incidents,
        maximum_unmatched_reconciliations,
        definition_hash,
        config.config_hash,
    )


def evaluate_burn_in(
    protocol: PaperBurnInProtocol,
    *,
    snapshots: tuple[PaperOperatorSnapshot, ...],
    evaluated_at: datetime,
) -> PaperBurnInAssessment:
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise ValueError("Phase 9B evaluation time must be UTC")
    ordered = tuple(sorted(snapshots, key=lambda item: (item.observed_at, item.snapshot_id)))
    if len({item.snapshot_id for item in ordered}) != len(ordered):
        raise ValueError("Phase 9B snapshot identities must be unique")
    if any(
        item.session_id != protocol.session_id
        or not protocol.window_start <= item.observed_at <= protocol.window_end
        or item.observed_at > evaluated_at
        for item in ordered
    ):
        raise ValueError("Phase 9B snapshot is outside the causal protocol window")
    attention_count = sum(item.health is not OperatorHealth.HEALTHY for item in ordered)
    count = len(ordered)
    attention_fraction = (
        Decimal(attention_count) / Decimal(count) if count else Decimal(0)
    )
    maximum_incidents = max((item.incident_count for item in ordered), default=0)
    maximum_unmatched = max(
        (item.unmatched_reconciliation_count for item in ordered), default=0
    )
    reasons: set[str] = set()
    if evaluated_at < protocol.window_end:
        reasons.add("WINDOW_OPEN")
    if count < protocol.minimum_observations:
        reasons.add("INSUFFICIENT_OBSERVATIONS")
    failures: set[str] = set()
    if attention_fraction > protocol.maximum_attention_fraction:
        failures.add("ATTENTION_FRACTION_EXCEEDED")
    if maximum_incidents > protocol.maximum_incidents:
        failures.add("INCIDENT_LIMIT_EXCEEDED")
    if maximum_unmatched > protocol.maximum_unmatched_reconciliations:
        failures.add("UNMATCHED_RECONCILIATION_LIMIT_EXCEEDED")
    if any(item.health is OperatorHealth.HALTED for item in ordered):
        failures.add("HALTED_SNAPSHOT_PRESENT")
    if reasons:
        state = BurnInState.INCONCLUSIVE
        reasons.update(failures)
    elif failures:
        state = BurnInState.FAIL
        reasons = failures
    else:
        state = BurnInState.PASS
    reason_codes = tuple(sorted(reasons))
    snapshot_root = canonical_hash(tuple(canonical_hash(item) for item in ordered))
    identity = (
        protocol.protocol_id,
        evaluated_at,
        state,
        count,
        attention_count,
        attention_fraction,
        maximum_incidents,
        maximum_unmatched,
        snapshot_root,
        reason_codes,
    )
    return PaperBurnInAssessment(
        deterministic_id("paper_burn_in_assessment", identity),
        protocol.protocol_id,
        protocol.session_id,
        evaluated_at,
        state,
        count,
        attention_count,
        attention_fraction,
        maximum_incidents,
        maximum_unmatched,
        snapshot_root,
        reason_codes,
        protocol.definition_hash,
        protocol.config_hash,
    )
