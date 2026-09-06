from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_phase8a_range_confirmatory import cohort
from trading_system.research.range_confirmatory import (
    evaluate_confirmatory_family,
    load_range_confirmatory_config,
)
from trading_system.research.range_confirmatory_export import (
    RangeConfirmatoryExportConfigError,
    load_range_confirmatory_export_config,
    render_range_confirmatory_markdown,
    write_range_confirmatory_export,
)
from trading_system.research.range_confirmatory_report import (
    RangeConfirmatoryReport,
    build_range_confirmatory_report,
    load_range_confirmatory_report_config,
)

ROOT = Path(__file__).parents[2]


def _report() -> RangeConfirmatoryReport:
    analysis = load_range_confirmatory_config(
        ROOT / "config/range_reclaim.phase8a.v1.yaml"
    )
    tests = evaluate_confirmatory_family(
        analysis,
        cohorts=(
            cohort("summary-b", ("1", "-1", "0")),
            cohort("summary-a", tuple("1" for _ in range(10))),
        ),
        familywise_alpha=Decimal("0.05"),
    )
    return build_range_confirmatory_report(
        load_range_confirmatory_report_config(
            ROOT / "config/range_reclaim.phase8c.v1.yaml"
        ),
        plan_id="plan-1",
        tests=tuple(reversed(tests)),
        analysis_config_hash=analysis.config_hash,
        adapter_config_hash="sha256:adapter",
    )


def test_phase8d_markdown_is_deterministic_complete_and_non_authoritative() -> None:
    content = render_range_confirmatory_markdown(_report())
    assert content == render_range_confirmatory_markdown(_report())
    assert b"\r\n" not in content
    assert b"## Identity" in content
    assert b"## Disclosures" in content
    assert b"## Confirmatory family" in content
    assert content.index(b"summary-a") < content.index(b"summary-b")
    assert b"Null rejection is not an efficacy claim" in content
    assert b"grants no parameter-selection or production authority" in content


def test_phase8d_write_receipt_matches_exact_file_bytes(tmp_path: Path) -> None:
    config = load_range_confirmatory_export_config(
        ROOT / "config/range_reclaim.phase8d.v1.yaml"
    )
    output = tmp_path / "nested" / "report.md"
    first = write_range_confirmatory_export(_report(), output=output, config=config)
    second = write_range_confirmatory_export(_report(), output=output, config=config)
    content = output.read_bytes()
    assert first == second
    assert first.output_path == str(output.resolve())
    assert first.byte_count == len(content)
    assert first.content_hash == f"sha256:{hashlib.sha256(content).hexdigest()}"
    assert not first.network_used
    assert not first.approval_granted
    assert not first.production_authority


def test_phase8d_config_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase8d.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeConfirmatoryExportConfigError, match="authority"):
        load_range_confirmatory_export_config(unsafe)
