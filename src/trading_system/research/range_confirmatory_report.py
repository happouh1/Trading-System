"""Non-interpretive Phase 8C reports over verified Phase 8B test families."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.domain import Direction, Timeframe
from trading_system.research.range_confirmatory import RangeConfirmatoryTest
from trading_system.serialization import canonical_hash, deterministic_id


class RangeConfirmatoryReportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryReportConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryReportRow:
    test_id: str
    summary_id: str
    fold_id: str
    timeframe: Timeframe
    direction: Direction
    horizon_bars: int
    cluster_count: int
    positive_count: int
    negative_count: int
    zero_count: int
    raw_p_value: Decimal
    holm_adjusted_p_value: Decimal
    familywise_alpha: Decimal
    null_hypothesis_status: str

    def __post_init__(self) -> None:
        if (
            not self.test_id
            or not self.summary_id
            or not self.fold_id
            or self.horizon_bars <= 0
            or min(
                self.cluster_count, self.positive_count, self.negative_count,
                self.zero_count,
            ) < 0
            or self.cluster_count
            != self.positive_count + self.negative_count + self.zero_count
            or not Decimal(0) <= self.raw_p_value <= Decimal(1)
            or not Decimal(0) <= self.holm_adjusted_p_value <= Decimal(1)
            or not Decimal(0) < self.familywise_alpha < Decimal(1)
            or self.null_hypothesis_status not in {"REJECTED", "NOT_REJECTED"}
        ):
            raise ValueError("invalid Phase 8C report row")


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryReport:
    report_id: str
    plan_id: str
    rows: tuple[RangeConfirmatoryReportRow, ...]
    family_size: int
    rejected_null_count: int
    analysis_config_hash: str
    adapter_config_hash: str
    report_config_hash: str
    disclosures: tuple[str, ...]
    report_version: str = "8C.1.0"
    efficacy_claimed: bool = False
    parameter_selection_performed: bool = False
    ranking_performed: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.report_id
            or not self.plan_id
            or self.family_size != len(self.rows)
            or self.rejected_null_count
            != sum(row.null_hypothesis_status == "REJECTED" for row in self.rows)
            or tuple(row.summary_id for row in self.rows)
            != tuple(sorted(row.summary_id for row in self.rows))
            or len(set(row.summary_id for row in self.rows)) != len(self.rows)
            or not all(
                value.startswith("sha256:")
                for value in (
                    self.analysis_config_hash,
                    self.adapter_config_hash,
                    self.report_config_hash,
                )
            )
            or not self.disclosures
            or self.report_version != "8C.1.0"
            or any(
                (
                    self.efficacy_claimed,
                    self.parameter_selection_performed,
                    self.ranking_performed,
                    self.production_authority,
                )
            )
        ):
            raise ValueError("invalid Phase 8C report")


def load_range_confirmatory_report_config(
    path: str | Path,
) -> RangeConfirmatoryReportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "report_version", "source", "ordering", "interpretation",
        "required_disclosures", "authority",
    }:
        raise RangeConfirmatoryReportConfigError("Phase 8C configuration keys are invalid")
    expected_disclosures = [
        "NO_EFFECT_SIZE_OR_INTERVAL_SPECIFIED",
        "NULL_REJECTION_IS_NOT_AN_EFFICACY_CLAIM",
        "NO_PARAMETER_SELECTION_OR_RANKING",
        "RESEARCH_ONLY_NO_PRODUCTION_AUTHORITY",
    ]
    if (
        raw["report_version"] != "8C.1.0"
        or raw["source"] != "PHASE8B_COMPLETE_VERIFIED_CONFIRMATORY_FAMILY"
        or raw["ordering"] != "SUMMARY_ID_ASCENDING"
        or raw["interpretation"] != "NULL_HYPOTHESIS_STATUS_ONLY"
        or raw["required_disclosures"] != expected_disclosures
    ):
        raise RangeConfirmatoryReportConfigError("Phase 8C report policy is invalid")
    authority = raw["authority"]
    if not isinstance(authority, dict) or set(authority) != {
        "efficacy_claims_enabled", "parameter_selection_enabled", "ranking_enabled",
        "scoring_enabled", "decision_changes_enabled", "alerts_enabled",
        "options_routing_enabled", "broker_writes_enabled", "live_trading_enabled",
    } or any(value is not False for value in authority.values()):
        raise RangeConfirmatoryReportConfigError("Phase 8C authority must remain disabled")
    frozen = {
        key: tuple(value) if isinstance(value, list)
        else MappingProxyType(dict(value)) if isinstance(value, dict)
        else value
        for key, value in raw.items()
    }
    return RangeConfirmatoryReportConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_range_confirmatory_report(
    config: RangeConfirmatoryReportConfig,
    *,
    plan_id: str,
    tests: tuple[RangeConfirmatoryTest, ...],
    analysis_config_hash: str,
    adapter_config_hash: str,
) -> RangeConfirmatoryReport:
    if (
        not plan_id
        or not analysis_config_hash.startswith("sha256:")
        or not adapter_config_hash.startswith("sha256:")
    ):
        raise ValueError("complete Phase 8C source identity is required")
    ordered = tuple(sorted(tests, key=lambda item: item.summary_id))
    if any(item.plan_id != plan_id for item in ordered):
        raise ValueError("Phase 8B test plan mismatch")
    if any(item.config_hash != analysis_config_hash for item in ordered):
        raise ValueError("Phase 8B test family has mixed analysis configurations")
    rows = tuple(
        RangeConfirmatoryReportRow(
            item.test_id, item.summary_id, item.fold_id, item.timeframe, item.direction,
            item.horizon_bars, item.cluster_count, item.positive_count,
            item.negative_count, item.zero_count, item.raw_p_value,
            item.holm_adjusted_p_value, item.familywise_alpha,
            "REJECTED" if item.null_rejected else "NOT_REJECTED",
        )
        for item in ordered
    )
    raw_disclosures = config.values["required_disclosures"]
    if not isinstance(raw_disclosures, tuple) or not all(
        isinstance(item, str) for item in raw_disclosures
    ):
        raise ValueError("Phase 8C disclosures are invalid")
    disclosures: tuple[str, ...] = tuple(str(item) for item in raw_disclosures)
    identity = (
        plan_id, rows, analysis_config_hash, adapter_config_hash, config.config_hash, "8C.1.0",
    )
    return RangeConfirmatoryReport(
        deterministic_id("range_confirmatory_report", identity), plan_id, rows, len(rows),
        sum(item.null_rejected for item in ordered), analysis_config_hash, adapter_config_hash,
        config.config_hash, disclosures,
    )
