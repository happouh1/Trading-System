"""Read-only terminal authority boundary for the Phase 8 confirmatory chain."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.research.range_confirmatory_export_registry import (
    RangeConfirmatoryExportStatus,
)
from trading_system.serialization import canonical_hash, deterministic_id

_TERMINAL_POLICY = "NO_EFFECT_SIZE_EFFICACY_SELECTION_OR_PRODUCTION_CHAIN"


class RangeConfirmatoryTerminalConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryTerminalConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryTerminalAssessment:
    assessment_id: str
    export_id: str
    report_id: str
    content_hash: str
    byte_count: int
    config_hash: str
    boundary_version: str = "8E.1.0"
    upstream_verified: bool = True
    terminal_boundary: bool = True
    effect_size_reported: bool = False
    uncertainty_interval_reported: bool = False
    economic_threshold_applied: bool = False
    fold_pooling_performed: bool = False
    efficacy_claimed: bool = False
    parameter_selection_performed: bool = False
    ranking_performed: bool = False
    approval_granted: bool = False
    network_used: bool = False
    broker_write_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.assessment_id, self.export_id, self.report_id))
            or not self.content_hash.startswith("sha256:")
            or self.byte_count <= 0
            or not self.config_hash.startswith("sha256:")
            or self.boundary_version != "8E.1.0"
            or not self.upstream_verified
            or not self.terminal_boundary
            or any(
                (
                    self.effect_size_reported,
                    self.uncertainty_interval_reported,
                    self.economic_threshold_applied,
                    self.fold_pooling_performed,
                    self.efficacy_claimed,
                    self.parameter_selection_performed,
                    self.ranking_performed,
                    self.approval_granted,
                    self.network_used,
                    self.broker_write_performed,
                    self.production_authority,
                )
            )
        ):
            raise ValueError("invalid Phase 8E terminal-boundary assessment")


def load_range_confirmatory_terminal_config(
    path: str | Path,
) -> RangeConfirmatoryTerminalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "boundary_version",
        "source",
        "terminal_policy",
        "required_export_version",
        "authority",
    }:
        raise RangeConfirmatoryTerminalConfigError(
            "Phase 8E configuration keys are invalid"
        )
    if (
        raw["boundary_version"] != "8E.1.0"
        or raw["source"] != "VALIDATED_PHASE8D_LOCAL_EXPORT"
        or raw["terminal_policy"] != _TERMINAL_POLICY
        or raw["required_export_version"] != "8D.1.0"
    ):
        raise RangeConfirmatoryTerminalConfigError(
            "Phase 8E terminal policy is invalid"
        )
    authority = raw["authority"]
    expected_authority = {
        "effect_size_enabled",
        "uncertainty_interval_enabled",
        "economic_threshold_enabled",
        "fold_pooling_enabled",
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
        raise RangeConfirmatoryTerminalConfigError(
            "Phase 8E authority must remain disabled"
        )
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeConfirmatoryTerminalConfig(
        MappingProxyType(frozen), canonical_hash(raw)
    )


def assess_range_confirmatory_terminal_boundary(
    config: RangeConfirmatoryTerminalConfig,
    export_status: RangeConfirmatoryExportStatus,
) -> RangeConfirmatoryTerminalAssessment:
    if not export_status.verified:
        raise ValueError("Phase 8D export is not verified")
    if export_status.export_version != "8D.1.0":
        raise ValueError("Phase 8D export version is unsupported")
    if not export_status.content_hash.startswith("sha256:") or export_status.byte_count <= 0:
        raise ValueError("Phase 8D export identity is incomplete")
    identity = (
        export_status.export_id,
        export_status.report_id,
        export_status.content_hash,
        export_status.byte_count,
        config.config_hash,
        "8E.1.0",
    )
    return RangeConfirmatoryTerminalAssessment(
        deterministic_id("range_confirmatory_terminal_assessment", identity),
        export_status.export_id,
        export_status.report_id,
        export_status.content_hash,
        export_status.byte_count,
        config.config_hash,
    )
