from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.test_phase7h_range_evaluation_report import evaluation
from trading_system.patterns import (
    build_range_evaluation_report,
    load_range_evaluation_report_config,
)
from trading_system.reporting import (
    RangeReportExportConfigError,
    load_range_report_export_config,
    render_persisted_range_evaluation,
)
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]


def payloads() -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    result = evaluation()
    report = build_range_evaluation_report(
        load_range_evaluation_report_config(
            ROOT / "config/range_reclaim.phase7h.v1.yaml"
        ),
        result,
    )
    report_payload = json.loads(canonical_json(report))
    summaries = tuple(json.loads(canonical_json(item)) for item in result.summaries)
    assert isinstance(report_payload, dict)
    assert all(isinstance(item, dict) for item in summaries)
    return report_payload, summaries


def test_export_is_deterministic_nonranking_and_offline() -> None:
    config = load_range_report_export_config(ROOT / "config/range_reclaim.phase7i.v1.yaml")
    report, summaries = payloads()
    first = render_persisted_range_evaluation(config, report, summaries)
    second = render_persisted_range_evaluation(config, report, tuple(reversed(summaries)))
    assert first == second
    assert "canonical order; not ranked" in first
    assert "WITHHELD_GATE_FAILED" in first
    assert "no recomputation" in first


def test_export_rejects_inconsistent_persisted_payload() -> None:
    config = load_range_report_export_config(ROOT / "config/range_reclaim.phase7i.v1.yaml")
    report, summaries = payloads()
    report["cohort_count"] = 99
    with pytest.raises(ValueError, match="cohort count"):
        render_persisted_range_evaluation(config, report, summaries)


def test_phase7i_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7i.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["recomputation_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReportExportConfigError, match="export-only"):
        load_range_report_export_config(unsafe)
