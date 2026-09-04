from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase7b_range_research import replay, research_bars
from trading_system.patterns import (
    RangeExperimentConfigError,
    RangeExperimentMaterialization,
    load_range_experiment_config,
    materialize_range_experiment,
    preregister_range_experiment,
)
from trading_system.research.orchestration import DatasetPartition

ROOT = Path(__file__).parents[2]


def sessions() -> tuple[date, ...]:
    start = date(2024, 9, 1)
    return tuple(start + timedelta(days=index) for index in range(700))


def materialization() -> RangeExperimentMaterialization:
    result = replay().run(research_bars())
    config = load_range_experiment_config(ROOT / "config/range_reclaim.phase7c.v1.yaml")
    plan = preregister_range_experiment(
        config,
        registered_at=datetime(2024, 8, 1, tzinfo=UTC),
        source_run_ids=("range-research-run",),
        universe_revision="fixture-universe-v1",
        box_config_hash="sha256:box",
        label_config_hash="sha256:labels",
        code_version="test",
    )
    return materialize_range_experiment(
        plan, boxes=result.boxes, outcomes=result.outcomes, sessions=sessions()
    )


def test_plan_and_assignments_are_deterministic_and_causal() -> None:
    first = materialization()
    second = materialization()
    assert first == second
    assert first.folds
    assert first.assignments
    assert all(item.cluster_id == item.box_id for item in first.assignments)
    assert any(item.partition is DatasetPartition.VALIDATION for item in first.assignments)
    assert all(
        item.reason == "ELIGIBLE"
        for item in first.assignments
        if item.partition is not DatasetPartition.EXCLUDED
    )


def test_small_fixture_fails_preregistered_evidence_gates() -> None:
    result = materialization()
    assert result.gates
    assert all(not gate.passed for gate in result.gates)
    assert all(gate.independent_cluster_count == 1 for gate in result.gates)


def test_materialization_rejects_missing_box_and_reordered_sessions() -> None:
    result = replay().run(research_bars())
    built = materialization()
    with pytest.raises(ValueError, match="supplied box"):
        materialize_range_experiment(
            built.plan, boxes=(), outcomes=result.outcomes, sessions=sessions()
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        materialize_range_experiment(
            built.plan,
            boxes=result.boxes,
            outcomes=result.outcomes,
            sessions=tuple(reversed(sessions())),
        )


def test_phase7c_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7c.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["scoring_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeExperimentConfigError, match="preregistration-only"):
        load_range_experiment_config(unsafe)
