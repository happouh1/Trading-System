from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper.operator_control import (
    PaperOperatorConfigError,
    build_operator_jobs,
    load_paper_operator_config,
)
from trading_system.research.range_replication_collection import (
    RangeReplicationFreezeManifest,
)
from trading_system.research.range_replication_runner import (
    RangeReplicationRunnerConfigError,
    load_range_replication_runner_config,
    run_replication_rehearsal,
)
from trading_system.research.range_replication_statistics import (
    RangeReplicationHypothesis,
    load_range_replication_statistics_config,
)

ROOT = Path(__file__).parents[2]
D = Decimal


def _freeze() -> RangeReplicationFreezeManifest:
    frozen_at = datetime(2026, 9, 7, 12, tzinfo=UTC)
    return RangeReplicationFreezeManifest(
        "freeze-test-8k",
        "collection-test-8k",
        frozen_at,
        12,
        12,
        "sha256:predictions",
        "sha256:outcomes",
        "sha256:manifest",
    )


def _hypothesis(identity: str, value: str) -> RangeReplicationHypothesis:
    return RangeReplicationHypothesis(
        identity,
        tuple((f"box-{index:02d}", D(value)) for index in range(12)),
    )


def test_phase8k_runner_is_deterministic_canonical_and_non_authoritative() -> None:
    runner_config = load_range_replication_runner_config(
        ROOT / "config/range_reclaim.phase8k.v1.yaml"
    )
    statistics_config = load_range_replication_statistics_config(
        ROOT / "config/range_reclaim.phase8g.v1.yaml"
    )
    first = run_replication_rehearsal(
        runner_config,
        statistics_config,
        hypotheses=(_hypothesis("h-b", "0.10"), _hypothesis("h-a", "0.30")),
        freeze=_freeze(),
        executed_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
        familywise_alpha=D("0.05"),
        economic_threshold_net_r=D("0.20"),
        minimum_total_clusters=10,
        minimum_nonzero_clusters=10,
    )
    second = run_replication_rehearsal(
        runner_config,
        statistics_config,
        hypotheses=(_hypothesis("h-a", "0.30"), _hypothesis("h-b", "0.10")),
        freeze=_freeze(),
        executed_at=datetime(2026, 9, 8, 12, tzinfo=UTC),
        familywise_alpha=D("0.05"),
        economic_threshold_net_r=D("0.20"),
        minimum_total_clusters=10,
        minimum_nonzero_clusters=10,
    )
    assert first == second
    assert tuple(result.hypothesis_id for result in first[1]) == ("h-a", "h-b")
    assert not first[0].efficacy_claimed
    assert not first[0].production_authority


def test_phase8k_rejects_future_execution_and_widened_authority(tmp_path: Path) -> None:
    runner_config = load_range_replication_runner_config(
        ROOT / "config/range_reclaim.phase8k.v1.yaml"
    )
    statistics_config = load_range_replication_statistics_config(
        ROOT / "config/range_reclaim.phase8g.v1.yaml"
    )
    with pytest.raises(ValueError, match="before the collection freeze"):
        run_replication_rehearsal(
            runner_config,
            statistics_config,
            freeze=_freeze(),
            hypotheses=(_hypothesis("h-a", "0.30"),),
            executed_at=datetime(2026, 9, 7, 11, tzinfo=UTC),
            familywise_alpha=D("0.05"),
            economic_threshold_net_r=D("0.20"),
            minimum_total_clusters=10,
            minimum_nonzero_clusters=10,
        )
    raw = json.loads(
        (ROOT / "config/range_reclaim.phase8k.v1.yaml").read_text(encoding="utf-8")
    )
    raw["authority"]["efficacy_claims_enabled"] = True
    unsafe = tmp_path / "unsafe-8k.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationRunnerConfigError, match="authority"):
        load_range_replication_runner_config(unsafe)


def test_phase9a_schedule_is_deterministic_and_planning_only() -> None:
    config = load_paper_operator_config(ROOT / "config/paper.phase9a.v1.yaml")
    anchor = datetime(2026, 9, 7, 12, tzinfo=UTC)
    first = build_operator_jobs(config, session_id="paper-9a", anchor_at=anchor)
    second = build_operator_jobs(config, session_id="paper-9a", anchor_at=anchor)
    assert first == second
    assert tuple(job.component for job in first) == (
        "PAPER_HEALTH_CHECK",
        "RECONCILIATION_CHECK",
        "REPLICATION_STATUS_CHECK",
    )
    assert first[0].due_at == anchor + timedelta(seconds=300)
    assert all(job.planning_only for job in first)


def test_phase9a_rejects_automatic_recovery(tmp_path: Path) -> None:
    raw = json.loads((ROOT / "config/paper.phase9a.v1.yaml").read_text(encoding="utf-8"))
    raw["authority"]["automatic_recovery_enabled"] = True
    unsafe = tmp_path / "unsafe-9a.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PaperOperatorConfigError, match="authority"):
        load_paper_operator_config(unsafe)
