from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.test_phase7c_range_experiment import materialization
from tests.unit.test_phase7d_range_trigger import range_box
from tests.unit.test_phase7f_range_outcome import (
    config as outcome_config,
)
from tests.unit.test_phase7f_range_outcome import filled_entry, outcome_candles
from trading_system.patterns import (
    RangeEntryOutcome,
    RangeEvaluationConfigError,
    evaluate_range_outcomes,
    label_range_entries,
    load_range_evaluation_config,
)
from trading_system.research.orchestration import DatasetPartition

ROOT = Path(__file__).parents[2]


def outcomes() -> tuple[RangeEntryOutcome, ...]:
    return label_range_entries(
        outcome_config(),
        entries=(filled_entry(),),
        boxes=(range_box(),),
        candles=outcome_candles(),
    )


def test_phase7g_retains_horizons_and_rechecks_frozen_gates() -> None:
    experiment = materialization()
    result = evaluate_range_outcomes(
        load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml"),
        experiment=experiment,
        outcomes=outcomes(),
    )
    assert {item.horizon_bars for item in result.assignments} == {1, 3, 5}
    assert result.summaries
    assert all(not item.gate_passed and item.statistics is None for item in result.summaries)


def test_statistics_exist_only_when_both_evidence_gates_pass() -> None:
    experiment = materialization()
    permissive = replace(
        experiment,
        plan=replace(experiment.plan, minimum_observations=1, minimum_clusters=1),
    )
    result = evaluate_range_outcomes(
        load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml"),
        experiment=permissive,
        outcomes=outcomes(),
    )
    assert all(item.gate_passed and item.statistics is not None for item in result.summaries)
    assert all(
        item.statistics is not None and item.statistics.count == item.observation_count
        for item in result.summaries
    )


def test_future_known_label_is_excluded_and_permutations_normalize() -> None:
    experiment = materialization()
    source = outcomes()
    future = replace(source[0], label_available_at=datetime(2030, 1, 1, tzinfo=UTC))
    config = load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml")
    first = evaluate_range_outcomes(
        config, experiment=experiment, outcomes=(future, *source[1:])
    )
    second = evaluate_range_outcomes(
        config, experiment=experiment, outcomes=tuple(reversed((future, *source[1:])))
    )
    assert first == second
    affected = [item for item in first.assignments if item.outcome_id == future.outcome_id]
    assert affected
    assert all(item.partition is DatasetPartition.EXCLUDED for item in affected)
    assert all(item.reason == "PHASE7F_LABEL_UNAVAILABLE_AT_CUTOFF" for item in affected)


def test_unregistered_outcome_and_duplicate_identity_fail_closed() -> None:
    experiment = materialization()
    source = outcomes()
    config = load_range_evaluation_config(ROOT / "config/range_reclaim.phase7g.v1.yaml")
    with pytest.raises(ValueError, match="identities"):
        evaluate_range_outcomes(config, experiment=experiment, outcomes=(source[0], source[0]))
    unmatched = replace(source[0], outcome_id="unmatched-outcome", box_id="unmatched-box")
    with pytest.raises(ValueError, match="no Phase 7C assignment"):
        evaluate_range_outcomes(config, experiment=experiment, outcomes=(unmatched,))
    mismatched = replace(source[0], outcome_id="mismatched-outcome", symbol="MSFT")
    with pytest.raises(ValueError, match="disagrees"):
        evaluate_range_outcomes(config, experiment=experiment, outcomes=(mismatched,))


def test_phase7g_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7g.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["scoring_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeEvaluationConfigError, match="descriptive-only"):
        load_range_evaluation_config(unsafe)
