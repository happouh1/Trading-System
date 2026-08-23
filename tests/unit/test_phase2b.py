from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.research.contracts import ResearchRow, WalkForwardFold
from trading_system.research.evaluation import evaluate_cohort
from trading_system.research.orchestration import (
    CohortSpec,
    DatasetPartition,
    ExperimentStage,
    assign_fold_rows,
    symbol_holdout_bucket,
    transition,
)
from trading_system.research.orchestration_config import load_orchestration_config

ROOT = Path(__file__).parents[2]


def fold() -> WalkForwardFold:
    return WalkForwardFold(
        "fold-1",
        "experiment-1",
        0,
        date(2026, 1, 1),
        date(2026, 1, 3),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 8),
        date(2026, 1, 9),
    )


def row(row_id: str, session: date, available: date) -> ResearchRow:
    return ResearchRow(
        row_id,
        f"observation-{row_id}",
        "AAPL",
        session,
        datetime.combine(available, datetime.min.time(), tzinfo=UTC),
        "SUCCESS",
        Decimal("1"),
    )


def test_fold_assignment_records_embargo_and_unavailable_labels() -> None:
    assignments = assign_fold_rows(
        "experiment-1",
        fold(),
        (
            row("train", date(2026, 1, 2), date(2026, 1, 3)),
            row("embargo", date(2026, 1, 4), date(2026, 1, 4)),
            row("future", date(2026, 1, 5), date(2026, 1, 7)),
            row("test", date(2026, 1, 8), date(2026, 1, 9)),
        ),
    )
    assert tuple(item.partition for item in assignments) == (
        DatasetPartition.TRAIN,
        DatasetPartition.EXCLUDED,
        DatasetPartition.EXCLUDED,
        DatasetPartition.TEST,
    )
    assert assignments[2].reason == "LABEL_UNAVAILABLE_AT_CUTOFF"


def test_lifecycle_requires_order_and_freeze_hash() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="invalid"):
        transition("experiment-1", ExperimentStage.DEFINED, ExperimentStage.FROZEN, occurred_at=now)
    with pytest.raises(ValueError, match="definition hash"):
        transition(
            "experiment-1",
            ExperimentStage.VALIDATION_EVALUATED,
            ExperimentStage.FROZEN,
            occurred_at=now,
        )


def test_symbol_holdout_is_stable_and_case_normalized() -> None:
    assert symbol_holdout_bucket("aapl") == symbol_holdout_bucket("AAPL")
    assert 0 <= symbol_holdout_bucket("AAPL") < 5


def test_declared_cohort_reports_small_sample_without_ranking() -> None:
    rows = (row("train", date(2026, 1, 2), date(2026, 1, 3)),)
    assignments = assign_fold_rows("experiment-1", fold(), rows)
    result = evaluate_cohort(
        CohortSpec("all", "experiment-1", "all", minimum_sample=30),
        DatasetPartition.TRAIN,
        assignments,
        rows,
        seed=7,
        bootstrap_samples=10,
    )
    assert result.eligible_count == 1
    assert result.sample_status == "INSUFFICIENT_SAMPLE"


def test_phase2b_config_is_strict_and_versioned() -> None:
    config = load_orchestration_config(ROOT / "config/research.phase2b.v1.yaml")
    assert config.minimum_cohort_sample == 30
    assert config.symbol_holdout_buckets == 5
    assert config.config_hash.startswith("sha256:")
