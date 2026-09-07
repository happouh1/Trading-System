from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.research.range_replication_statistics import (
    RangeReplicationHypothesis,
    RangeReplicationStatisticsConfigError,
    ReplicationState,
    decimal_median,
    evaluate_replication_family,
    exact_median_lower_bound,
    load_range_replication_statistics_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/range_reclaim.phase8g.v1.yaml"
D = Decimal


def _hypothesis(identity: str, values: tuple[str, ...]) -> RangeReplicationHypothesis:
    return RangeReplicationHypothesis(
        identity,
        tuple((f"box-{index:03d}", D(value)) for index, value in enumerate(values)),
    )


def test_decimal_median_retains_zero_and_uses_exact_decimal_arithmetic() -> None:
    assert decimal_median((D("3"), D("0"), D("1"))) == D("1")
    assert decimal_median((D("4"), D("1"))) == D("2.5")
    with pytest.raises(ValueError, match="finite observations"):
        decimal_median(())


def test_exact_median_lower_bound_uses_conservative_order_statistic() -> None:
    values = tuple(D(value) for value in range(1, 11))
    assert exact_median_lower_bound(values, one_sided_alpha=D("0.05")) == D("2")
    assert exact_median_lower_bound((D("1"),), one_sided_alpha=D("0.05")) is None


def test_family_is_deterministic_and_replication_requires_both_gates() -> None:
    config = load_range_replication_statistics_config(CONFIG)
    strong = _hypothesis("h-strong", ("0.3",) * 12)
    weak = _hypothesis("h-weak", ("0.1",) * 12)
    first = evaluate_replication_family(
        config,
        hypotheses=(weak, strong),
        familywise_alpha=D("0.05"),
        economic_threshold_net_r=D("0.2"),
        minimum_total_clusters=10,
        minimum_nonzero_clusters=10,
    )
    second = evaluate_replication_family(
        config,
        hypotheses=(strong, weak),
        familywise_alpha=D("0.05"),
        economic_threshold_net_r=D("0.2"),
        minimum_total_clusters=10,
        minimum_nonzero_clusters=10,
    )
    assert first == second
    assert tuple(result.hypothesis_id for result in first) == ("h-strong", "h-weak")
    assert first[0].state is ReplicationState.REPLICATED
    assert first[1].state is ReplicationState.NOT_REPLICATED
    assert all(not result.production_authority for result in first)


def test_validity_or_sample_failure_is_inconclusive() -> None:
    config = load_range_replication_statistics_config(CONFIG)
    hypothesis = RangeReplicationHypothesis(
        "h-1",
        (("box-1", D("1")),),
        ("SAME_SYMBOL_WINDOW_OVERLAP",),
    )
    result = evaluate_replication_family(
        config,
        hypotheses=(hypothesis,),
        familywise_alpha=D("0.05"),
        economic_threshold_net_r=D("0.2"),
        minimum_total_clusters=10,
        minimum_nonzero_clusters=8,
    )[0]
    assert result.state is ReplicationState.INCONCLUSIVE
    assert result.reason_codes == (
        "INSUFFICIENT_NONZERO_CLUSTERS",
        "INSUFFICIENT_TOTAL_CLUSTERS",
        "NONTRIVIAL_INTERVAL_UNAVAILABLE",
        "SAME_SYMBOL_WINDOW_OVERLAP",
    )


def test_config_rejects_widened_authority_and_relaxed_prerequisite(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["cli_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationStatisticsConfigError, match="authority"):
        load_range_replication_statistics_config(unsafe)

    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["prerequisites"]["independent_review_attestation_required"] = False
    relaxed = tmp_path / "relaxed.json"
    relaxed.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationStatisticsConfigError, match="prerequisites"):
        load_range_replication_statistics_config(relaxed)


def test_hypothesis_rejects_permuted_or_duplicate_cluster_identity() -> None:
    with pytest.raises(ValueError, match="invalid Phase 8G hypothesis"):
        RangeReplicationHypothesis(
            "h-1",
            (("box-2", D("1")), ("box-1", D("1"))),
        )
    with pytest.raises(ValueError, match="invalid Phase 8G hypothesis"):
        RangeReplicationHypothesis(
            "h-1",
            (("box-1", D("1")), ("box-1", D("2"))),
        )
