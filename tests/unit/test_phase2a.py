from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.research.calibration import CalibrationObservation, calibration_report
from trading_system.research.config import load_research_config
from trading_system.research.contracts import (
    HumanReview,
    ResearchRow,
    ReviewVerdict,
    UniverseMembership,
    WalkForwardSpec,
    eligible_truth_reviews,
)
from trading_system.research.exports import (
    export_csv,
    export_jsonl,
    export_parquet,
    research_markdown,
)
from trading_system.research.folds import build_walk_forward_folds, eligible_labeled_rows
from trading_system.research.similarity import (
    SimilarityCandidate,
    fit_normalization,
    rank_similar,
)
from trading_system.research.statistics import summarize_returns
from trading_system.research.universe import PointInTimeUniverse

D = Decimal
ROOT = Path(__file__).parents[2]


def test_walk_forward_boundaries_are_expanding_and_embargoed() -> None:
    sessions = tuple(date(2026, 1, 1) + timedelta(days=index) for index in range(12))
    spec = WalkForwardSpec(4, 2, 2, 2, 1)
    folds = build_walk_forward_folds("experiment-1", sessions, spec)
    assert len(folds) == 2
    assert folds[0].train_start == sessions[0]
    assert folds[0].train_end == sessions[3]
    assert folds[0].validation_start == sessions[5]
    assert folds[0].test_start == sessions[8]
    assert folds[1].train_end == sessions[5]


def test_label_availability_must_precede_fold_cutoff() -> None:
    cutoff = date(2026, 1, 10)
    known = ResearchRow(
        "row-1",
        "observation-1",
        "AAPL",
        date(2026, 1, 5),
        datetime(2026, 1, 9, tzinfo=UTC),
        "SUCCESS",
        D("1"),
    )
    future = ResearchRow(
        "row-2",
        "observation-2",
        "AAPL",
        date(2026, 1, 5),
        datetime(2026, 1, 11, tzinfo=UTC),
        "SUCCESS",
        D("1"),
    )
    assert eligible_labeled_rows((future, known), cutoff=cutoff) == (known,)


def test_point_in_time_universe_respects_delisting_and_rejects_overlap() -> None:
    first = UniverseMembership.create(
        "OLD", date(2020, 1, 1), date(2020, 12, 31), "fixture", "revision-1"
    )
    current = UniverseMembership.create(
        "NEW", date(2021, 1, 1), None, "fixture", "revision-1"
    )
    universe = PointInTimeUniverse((current, first))
    assert universe.members_asof(date(2020, 6, 1)) == ("OLD",)
    assert universe.members_asof(date(2021, 6, 1)) == ("NEW",)
    overlap = UniverseMembership.create(
        "OLD", date(2020, 6, 1), None, "fixture", "revision-2"
    )
    with pytest.raises(ValueError, match="overlapping"):
        PointInTimeUniverse((first, overlap))


def test_statistics_and_bootstrap_are_deterministic() -> None:
    values = (D("1"), D("2"), D("-1"), D("0.5"))
    mfe = (D("2"), D("3"), D("0.5"), D("1"))
    mae = (D("0.5"), D("0.25"), D("1"), D("0.5"))
    first = summarize_returns(
        values, seed=7, bootstrap_samples=100, mfe_values=mfe, mae_values=mae
    )
    second = summarize_returns(
        values, seed=7, bootstrap_samples=100, mfe_values=mfe, mae_values=mae
    )
    assert first == second
    assert first.count == 4
    assert first.profit_factor == D("3.5")
    assert first.maximum_drawdown_r == D("1")
    assert first.p90_mfe_r is not None
    assert first.p90_mae_r is not None


def test_calibration_never_mutates_rule_confidence() -> None:
    observations = (
        CalibrationObservation("a", D("75"), True),
        CalibrationObservation("b", D("79"), False),
    )
    result = calibration_report(observations)
    assert observations[0].rule_confidence == D("75")
    assert result[0].count == 2
    assert result[0].observed_success_rate == D("0.5")


def test_similarity_uses_training_normalization_and_stable_tie_break() -> None:
    training = (
        {"x": D("0"), "y": D("0")},
        {"x": D("2"), "y": D("4")},
    )
    normalization = fit_normalization(training, ("x", "y"))
    candidates = (
        SimilarityCandidate("b", {"x": D("1"), "y": D("2")}),
        SimilarityCandidate("a", {"x": D("1"), "y": D("2")}),
        SimilarityCandidate("missing", {"x": None, "y": D("2")}),
    )
    ranked = rank_similar(
        {"x": D("1"), "y": D("2")},
        candidates,
        normalization,
        {"x": D("1"), "y": D("1")},
    )
    assert tuple(item.candidate_id for item in ranked) == ("a", "b")


def test_uncertain_review_is_not_training_truth() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    reviews = (
        HumanReview(
            "review-1", "experiment-1", "observation-1", "r1", now, ReviewVerdict.UNCERTAIN
        ),
        HumanReview(
            "review-2", "experiment-1", "observation-1", "r2", now, ReviewVerdict.CONFIRMED
        ),
    )
    assert eligible_truth_reviews(reviews) == (reviews[1],)


def test_phase2a_config_is_versioned_and_strict() -> None:
    config = load_research_config(ROOT / "config/research.phase2a.v1.yaml")
    assert config.config_hash.startswith("sha256:")
    assert config.section("similarity")["minimum_coverage"] == 0.60


def test_research_exports_are_deterministic_and_disclose_bias(tmp_path: Path) -> None:
    rows = ({"z": 2, "a": "value"}, {"a": "next", "z": 1})
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    export_jsonl(rows, first)
    export_jsonl(rows, second)
    assert first.read_bytes() == second.read_bytes()
    csv_path = tmp_path / "results.csv"
    export_csv(rows, csv_path)
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "a,z"
    parquet_path = tmp_path / "results.parquet"
    export_parquet(rows, parquet_path)
    assert parquet_path.stat().st_size > 0
    report = research_markdown("experiment-1", {"statistics": rows})
    assert "survivorship bias" in report.lower()
    assert "do not alter Phase 1" in report
