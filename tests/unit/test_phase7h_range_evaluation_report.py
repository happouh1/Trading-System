from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.unit.test_phase7c_range_experiment import materialization
from tests.unit.test_phase7d_range_trigger import range_box
from tests.unit.test_phase7f_range_outcome import config as outcome_config
from tests.unit.test_phase7f_range_outcome import filled_entry, outcome_candles
from trading_system.patterns import (
    RangeEvaluationReportConfigError,
    RangeEvaluationResult,
    build_range_evaluation_report,
    evaluate_range_outcomes,
    label_range_entries,
    load_range_evaluation_config,
    load_range_evaluation_report_config,
    range_evaluation_markdown,
)

ROOT = Path(__file__).parents[2]


def evaluation(*, pass_gates: bool = False) -> RangeEvaluationResult:
    experiment = materialization()
    if pass_gates:
        experiment = replace(
            experiment,
            plan=replace(experiment.plan, minimum_observations=1, minimum_clusters=1),
        )
    outcomes = label_range_entries(
        outcome_config(),
        entries=(filled_entry(),),
        boxes=(range_box(),),
        candles=outcome_candles(),
    )
    return evaluate_range_outcomes(
        load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml"),
        experiment=experiment,
        outcomes=outcomes,
    )


def test_report_is_deterministic_content_bound_and_nonranking() -> None:
    config = load_range_evaluation_report_config(
        ROOT / "config/range_reclaim.phase7h.v1.yaml"
    )
    result = evaluation()
    first = build_range_evaluation_report(config, result)
    second = build_range_evaluation_report(
        config,
        RangeEvaluationResult(
            tuple(reversed(result.assignments)), tuple(reversed(result.summaries))
        ),
    )
    assert first == second
    assert first.passing_cohort_count == 0
    body = range_evaluation_markdown(first, tuple(reversed(result.summaries)))
    assert "not ranked" in body
    assert "WITHHELD_GATE_FAILED" in body
    assert "NO_EFFICACY_CLAIM" in body


def test_passing_cohorts_are_rendered_without_selecting_one() -> None:
    config = load_range_evaluation_report_config(
        ROOT / "config/range_reclaim.phase7h.v1.yaml"
    )
    result = evaluation(pass_gates=True)
    report = build_range_evaluation_report(config, result)
    assert report.passing_cohort_count == report.cohort_count
    body = range_evaluation_markdown(report, result.summaries)
    assert "mean_net_directional_return" in body


def test_report_rejects_inconsistent_denominator() -> None:
    config = load_range_evaluation_report_config(
        ROOT / "config/range_reclaim.phase7h.v1.yaml"
    )
    result = evaluation()
    changed = replace(
        result.summaries[0], observation_count=result.summaries[0].observation_count + 1
    )
    corrupt = RangeEvaluationResult(result.assignments, (changed, *result.summaries[1:]))
    with pytest.raises(ValueError, match="observation denominator"):
        build_range_evaluation_report(config, corrupt)
    report = build_range_evaluation_report(config, result)
    with pytest.raises(ValueError, match="report root"):
        range_evaluation_markdown(report, corrupt.summaries)


def test_phase7h_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7h.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["ranking_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeEvaluationReportConfigError, match="audit-only"):
        load_range_evaluation_report_config(unsafe)
