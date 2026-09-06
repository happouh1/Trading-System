from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_phase8a_range_confirmatory import cohort
from trading_system.research.range_confirmatory import (
    evaluate_confirmatory_family,
    load_range_confirmatory_config,
)
from trading_system.research.range_confirmatory_report import (
    RangeConfirmatoryReportConfigError,
    build_range_confirmatory_report,
    load_range_confirmatory_report_config,
)

ROOT = Path(__file__).parents[2]


def test_phase8c_report_is_canonical_complete_and_non_authoritative() -> None:
    analysis = load_range_confirmatory_config(
        ROOT / "config/range_reclaim.phase8a.v1.yaml"
    )
    config = load_range_confirmatory_report_config(
        ROOT / "config/range_reclaim.phase8c.v1.yaml"
    )
    tests = evaluate_confirmatory_family(
        analysis,
        cohorts=(
            cohort("summary-b", ("1", "-1", "0")),
            cohort("summary-a", tuple("1" for _ in range(10))),
        ),
        familywise_alpha=Decimal("0.05"),
    )
    report = build_range_confirmatory_report(
        config,
        plan_id="plan-1",
        tests=tuple(reversed(tests)),
        analysis_config_hash=analysis.config_hash,
        adapter_config_hash="sha256:adapter",
    )
    assert tuple(row.summary_id for row in report.rows) == ("summary-a", "summary-b")
    assert report.family_size == 2
    assert report.rejected_null_count == 1
    assert not report.efficacy_claimed
    assert not report.ranking_performed
    assert "NO_EFFECT_SIZE_OR_INTERVAL_SPECIFIED" in report.disclosures


def test_phase8c_config_and_mixed_lineage_fail_closed(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase8c.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["efficacy_claims_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeConfirmatoryReportConfigError, match="authority"):
        load_range_confirmatory_report_config(unsafe)

    analysis = load_range_confirmatory_config(
        ROOT / "config/range_reclaim.phase8a.v1.yaml"
    )
    config = load_range_confirmatory_report_config(source)
    tests = evaluate_confirmatory_family(
        analysis,
        cohorts=(cohort("summary", ("1",)),),
        familywise_alpha=Decimal("0.05"),
    )
    with pytest.raises(ValueError, match="plan mismatch"):
        build_range_confirmatory_report(
            config,
            plan_id="different-plan",
            tests=tests,
            analysis_config_hash=analysis.config_hash,
            adapter_config_hash="sha256:adapter",
        )
