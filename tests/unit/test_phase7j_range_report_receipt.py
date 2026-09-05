from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.test_phase7i_range_report_export import payloads
from trading_system.reporting import (
    RangeReportReceiptConfigError,
    load_range_report_export_config,
    load_range_report_receipt_config,
    render_persisted_range_evaluation,
    write_atomic_range_report,
)

ROOT = Path(__file__).parents[2]


def test_atomic_receipt_is_deterministic_and_content_bound(tmp_path: Path) -> None:
    report, summaries = payloads()
    rendering = load_range_report_export_config(ROOT / "config/range_reclaim.phase7i.v1.yaml")
    config = load_range_report_receipt_config(ROOT / "config/range_reclaim.phase7j.v1.yaml")
    body = render_persisted_range_evaluation(rendering, report, summaries)
    output = tmp_path / "report.md"
    first = write_atomic_range_report(
        body=body,
        output=output,
        report=report,
        rendering_config_hash=rendering.config_hash,
        config=config,
    )
    second = write_atomic_range_report(
        body=body,
        output=output,
        report=report,
        rendering_config_hash=rendering.config_hash,
        config=config,
    )
    assert first == second
    assert output.read_bytes() == body.encode("utf-8")
    assert first.byte_count == len(body.encode("utf-8"))
    assert first.content_hash.startswith("sha256:")
    assert not tuple(tmp_path.glob(".range-report-*.tmp"))


def test_atomic_receipt_requires_existing_parent(tmp_path: Path) -> None:
    report, summaries = payloads()
    rendering = load_range_report_export_config(ROOT / "config/range_reclaim.phase7i.v1.yaml")
    config = load_range_report_receipt_config(ROOT / "config/range_reclaim.phase7j.v1.yaml")
    with pytest.raises(ValueError, match="parent directory"):
        write_atomic_range_report(
            body=render_persisted_range_evaluation(rendering, report, summaries),
            output=tmp_path / "missing" / "report.md",
            report=report,
            rendering_config_hash=rendering.config_hash,
            config=config,
        )


def test_phase7j_config_cannot_expand_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7j.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReportReceiptConfigError, match="local and export-only"):
        load_range_report_receipt_config(unsafe)
