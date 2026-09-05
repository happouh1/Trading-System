"""Local Markdown exports from verified persisted Phase 7H evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash, canonical_json


class RangeReportExportConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeReportExportConfig:
    values: Mapping[str, object]
    config_hash: str


def load_range_report_export_config(path: str | Path) -> RangeReportExportConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "export_version",
        "source",
        "format",
        "cohort_ordering",
        "failed_gate_value",
        "authority",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RangeReportExportConfigError("range export top-level keys are invalid")
    if (
        raw["export_version"] != "7I.1.0"
        or raw["source"] != "PERSISTED_VERIFIED_PHASE7H_REPORT_ONLY"
        or raw["format"] != "MARKDOWN"
        or raw["cohort_ordering"] != "FOLD_PARTITION_TIMEFRAME_DIRECTION_HORIZON"
        or raw["failed_gate_value"] != "WITHHELD_GATE_FAILED"
    ):
        raise RangeReportExportConfigError("Phase 7I export policy is invalid")
    if raw["authority"] != {
        "recomputation_enabled": False,
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
        raise RangeReportExportConfigError("Phase 7I authority must remain export-only")
    frozen = {
        key: MappingProxyType(dict(value)) if isinstance(value, dict) else value
        for key, value in raw.items()
    }
    return RangeReportExportConfig(MappingProxyType(frozen), canonical_hash(raw))


def render_persisted_range_evaluation(
    config: RangeReportExportConfig,
    report: Mapping[str, object],
    summaries: tuple[Mapping[str, object], ...],
) -> str:
    if config.values.get("failed_gate_value") != "WITHHELD_GATE_FAILED":
        raise ValueError("validated Phase 7I configuration is inconsistent")
    report_id = _string(report, "report_id")
    plan_id = _string(report, "plan_id")
    disclosures = report.get("disclosures")
    if not isinstance(disclosures, list) or not all(isinstance(item, str) for item in disclosures):
        raise ValueError("persisted report disclosures are invalid")
    if _integer(report, "cohort_count") != len(summaries):
        raise ValueError("persisted report cohort count is inconsistent")
    if any(_string(item, "plan_id") != plan_id for item in summaries):
        raise ValueError("persisted report summaries reference another plan")
    ordered = tuple(
        sorted(
            summaries,
            key=lambda item: (
                _string(item, "fold_id"),
                _string(item, "partition"),
                _string(item, "timeframe"),
                _string(item, "direction"),
                _integer(item, "horizon_bars"),
            ),
        )
    )
    lines = [
        f"# Range evaluation report: {report_id}",
        "",
        f"- Plan: `{plan_id}`",
        f"- Assignments: `{_integer(report, 'assignment_count')}`",
        f"- Included: `{_integer(report, 'included_assignment_count')}`",
        f"- Excluded: `{_integer(report, 'excluded_assignment_count')}`",
        f"- Cohorts: `{len(summaries)}`",
        f"- Passing evidence gates: `{_integer(report, 'passing_cohort_count')}`",
        f"- Assignment root: `{_string(report, 'assignment_root')}`",
        f"- Summary root: `{_string(report, 'summary_root')}`",
        "",
        "## Cohorts (canonical order; not ranked)",
        "",
    ]
    for item in ordered:
        label = "/".join(
            (
                _string(item, "fold_id"),
                _string(item, "partition"),
                _string(item, "timeframe"),
                _string(item, "direction"),
                str(_integer(item, "horizon_bars")),
            )
        )
        statistics = item.get("statistics")
        displayed = (
            "WITHHELD_GATE_FAILED" if statistics is None else canonical_json(statistics)
        )
        lines.append(
            f"- `{label}` observations={_integer(item, 'observation_count')} "
            f"clusters={_integer(item, 'independent_cluster_count')} statistics=`{displayed}`"
        )
    lines.extend(("", "## Disclosures", ""))
    lines.extend(f"- `{item}`" for item in disclosures)
    lines.extend(("", "Generated locally from verified persisted evidence; no recomputation.", ""))
    return "\n".join(lines)


def _string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"persisted report {key} must be a nonempty string")
    return item


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise ValueError(f"persisted report {key} must be a nonnegative integer")
    return item
