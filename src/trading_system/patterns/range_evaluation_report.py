"""Deterministic, non-ranking audit reports for Phase 7G evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.domain import Direction, Timeframe
from trading_system.patterns.range_evaluation import (
    RangeCohortSummary,
    RangeEvaluationAssignment,
    RangeEvaluationResult,
)
from trading_system.research.orchestration import DatasetPartition
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

DISCLOSURES = (
    "DESCRIPTIVE_RESEARCH_ONLY",
    "NO_MULTIPLE_TESTING_INFERENCE",
    "NO_EFFICACY_CLAIM",
    "NO_PARAMETER_OR_HORIZON_SELECTION",
    "NO_SCORING_OR_TRADING_AUTHORITY",
)
CohortKey = tuple[str, DatasetPartition, Timeframe, Direction, int]


class RangeEvaluationReportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeEvaluationReportConfig:
    values: Mapping[str, object]
    config_hash: str


def load_range_evaluation_report_config(
    path: str | Path,
) -> RangeEvaluationReportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected_keys = {"report_version", "ordering", "integrity", "disclosures", "authority"}
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise RangeEvaluationReportConfigError("range report top-level keys are invalid")
    if raw["report_version"] != "7H.1.0":
        raise RangeEvaluationReportConfigError("report_version must be 7H.1.0")
    if raw["ordering"] != "FOLD_PARTITION_TIMEFRAME_DIRECTION_HORIZON":
        raise RangeEvaluationReportConfigError("range report ordering is invalid")
    if raw["integrity"] != {
        "assignment_root": "CANONICAL_SHA256",
        "summary_root": "CANONICAL_SHA256",
        "verify_cohort_denominators": True,
        "verify_gate_statistics_consistency": True,
    }:
        raise RangeEvaluationReportConfigError("range report integrity policy is invalid")
    if raw["disclosures"] != list(DISCLOSURES):
        raise RangeEvaluationReportConfigError("range report disclosures are invalid")
    if raw["authority"] != {
        "ranking_enabled": False,
        "hypothesis_tests_enabled": False,
        "efficacy_claims_enabled": False,
        "parameter_selection_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeEvaluationReportConfigError("Phase 7H authority must remain audit-only")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else tuple(value)
        if isinstance(value, list)
        else value
        for key, value in raw.items()
    }
    return RangeEvaluationReportConfig(MappingProxyType(frozen), canonical_hash(raw))


@dataclass(frozen=True, slots=True)
class RangeEvaluationReport:
    report_id: str
    plan_id: str
    assignment_count: int
    included_assignment_count: int
    excluded_assignment_count: int
    cohort_count: int
    passing_cohort_count: int
    assignment_root: str
    summary_root: str
    disclosures: tuple[str, ...]
    config_hash: str
    report_version: str = "7H.1.0"

    def __post_init__(self) -> None:
        if not self.report_id or not self.plan_id or not self.config_hash:
            raise ValueError("complete range report identity is required")
        counts = (
            self.assignment_count,
            self.included_assignment_count,
            self.excluded_assignment_count,
            self.cohort_count,
            self.passing_cohort_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("range report counts cannot be negative")
        if self.included_assignment_count + self.excluded_assignment_count != self.assignment_count:
            raise ValueError("range report assignment denominator is inconsistent")
        if self.passing_cohort_count > self.cohort_count:
            raise ValueError("passing cohort count cannot exceed cohort count")
        if not self.assignment_root.startswith("sha256:") or not self.summary_root.startswith(
            "sha256:"
        ):
            raise ValueError("range report roots must use sha256")
        if self.disclosures != DISCLOSURES or self.report_version != "7H.1.0":
            raise ValueError("Phase 7H disclosures and version are fixed")


def build_range_evaluation_report(
    config: RangeEvaluationReportConfig,
    result: RangeEvaluationResult,
) -> RangeEvaluationReport:
    assignments = tuple(sorted(result.assignments, key=lambda item: item.assignment_id))
    summaries = tuple(sorted(result.summaries, key=lambda item: item.summary_id))
    if not assignments or not summaries:
        raise ValueError("range evaluation report requires assignments and summaries")
    plan_ids = {item.plan_id for item in assignments} | {item.plan_id for item in summaries}
    if len(plan_ids) != 1:
        raise ValueError("range evaluation report requires exactly one plan")
    _verify_denominators(assignments, summaries)
    assignment_root = canonical_hash(assignments)
    summary_root = canonical_hash(summaries)
    included = sum(item.partition is not DatasetPartition.EXCLUDED for item in assignments)
    identity = (next(iter(plan_ids)), assignment_root, summary_root, config.config_hash, "7H.1.0")
    return RangeEvaluationReport(
        deterministic_id("range_evaluation_report", identity),
        next(iter(plan_ids)),
        len(assignments),
        included,
        len(assignments) - included,
        len(summaries),
        sum(item.gate_passed for item in summaries),
        assignment_root,
        summary_root,
        DISCLOSURES,
        config.config_hash,
    )


def _cohort_key(item: RangeEvaluationAssignment) -> CohortKey:
    return (
        item.fold_id,
        item.partition,
        item.timeframe,
        item.direction,
        item.horizon_bars,
    )


def _verify_denominators(
    assignments: tuple[RangeEvaluationAssignment, ...],
    summaries: tuple[RangeCohortSummary, ...],
) -> None:
    groups: dict[CohortKey, list[RangeEvaluationAssignment]] = {}
    for item in assignments:
        if item.partition is not DatasetPartition.EXCLUDED:
            groups.setdefault(_cohort_key(item), []).append(item)
    summaries_by_key = {
        (item.fold_id, item.partition, item.timeframe, item.direction, item.horizon_bars): item
        for item in summaries
    }
    if len(summaries_by_key) != len(summaries) or set(summaries_by_key) != set(groups):
        raise ValueError("range evaluation cohort coverage is inconsistent")
    for key, group in groups.items():
        summary = summaries_by_key[key]
        if summary.observation_count != len(group):
            raise ValueError("range evaluation observation denominator is inconsistent")
        if summary.independent_cluster_count != len({item.cluster_id for item in group}):
            raise ValueError("range evaluation cluster denominator is inconsistent")
        if summary.gate_passed != (summary.statistics is not None):
            raise ValueError("range evaluation gate/statistics state is inconsistent")


def range_evaluation_markdown(
    report: RangeEvaluationReport,
    summaries: tuple[RangeCohortSummary, ...],
) -> str:
    source_order = tuple(sorted(summaries, key=lambda item: item.summary_id))
    if canonical_hash(source_order) != report.summary_root:
        raise ValueError("Phase 7H Markdown summaries do not match the report root")
    ordered = tuple(
        sorted(
            summaries,
            key=lambda item: (
                item.fold_id,
                item.partition.value,
                item.timeframe.value,
                item.direction.value,
                item.horizon_bars,
            ),
        )
    )
    lines = [
        f"# Range evaluation report: {report.report_id}",
        "",
        f"- Plan: `{report.plan_id}`",
        f"- Assignments: `{report.assignment_count}`",
        f"- Included: `{report.included_assignment_count}`",
        f"- Excluded: `{report.excluded_assignment_count}`",
        f"- Cohorts: `{report.cohort_count}`",
        f"- Passing evidence gates: `{report.passing_cohort_count}`",
        f"- Assignment root: `{report.assignment_root}`",
        f"- Summary root: `{report.summary_root}`",
        "",
        "## Cohorts (canonical order; not ranked)",
        "",
    ]
    for item in ordered:
        label = "/".join(
            (
                item.fold_id,
                item.partition.value,
                item.timeframe.value,
                item.direction.value,
                str(item.horizon_bars),
            )
        )
        statistics = "WITHHELD_GATE_FAILED" if item.statistics is None else canonical_json(
            item.statistics
        )
        lines.append(
            f"- `{label}` observations={item.observation_count} "
            f"clusters={item.independent_cluster_count} statistics=`{statistics}`"
        )
    lines.extend(("", "## Disclosures", ""))
    lines.extend(f"- `{item}`" for item in report.disclosures)
    lines.append("")
    return "\n".join(lines)
