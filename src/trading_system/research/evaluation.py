"""Declared-cohort evaluation without automated selection or ranking."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_system.research.contracts import ResearchRow
from trading_system.research.orchestration import CohortSpec, DatasetPartition, FoldAssignment
from trading_system.research.statistics import DescriptiveStatistics, summarize_returns


@dataclass(frozen=True, slots=True)
class CohortEvaluation:
    cohort_id: str
    partition: DatasetPartition
    eligible_count: int
    sample_status: str
    statistics: DescriptiveStatistics


def _matches(row: ResearchRow, cohort: CohortSpec) -> bool:
    return all(str(row.features.get(name)) == expected for name, expected in cohort.filters.items())


def evaluate_cohort(
    cohort: CohortSpec,
    partition: DatasetPartition,
    assignments: tuple[FoldAssignment, ...],
    rows: tuple[ResearchRow, ...],
    *,
    seed: int,
    bootstrap_samples: int = 1000,
) -> CohortEvaluation:
    eligible_ids = {
        item.row_id
        for item in assignments
        if item.partition is partition and item.reason == "ELIGIBLE"
    }
    selected = tuple(
        row
        for row in sorted(rows, key=lambda item: (item.session_date, item.row_id))
        if row.row_id in eligible_ids and row.net_r is not None and _matches(row, cohort)
    )
    values = tuple(row.net_r for row in selected if isinstance(row.net_r, Decimal))
    status = "SUFFICIENT_SAMPLE" if len(values) >= cohort.minimum_sample else "INSUFFICIENT_SAMPLE"
    return CohortEvaluation(
        cohort.cohort_id,
        partition,
        len(values),
        status,
        summarize_returns(values, seed=seed, bootstrap_samples=bootstrap_samples),
    )
