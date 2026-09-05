from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tests.unit.test_phase7h_range_evaluation_report import evaluation
from trading_system.patterns import (
    build_range_evaluation_report,
    load_range_evaluation_report_config,
)
from trading_system.reporting import (
    RangeEvidenceBundleConfigError,
    load_range_evidence_bundle_config,
    verify_range_evidence_bundle,
    write_range_evidence_bundle,
)
from trading_system.serialization import canonical_json

ROOT = Path(__file__).parents[2]


def evidence() -> tuple[
    dict[str, object], tuple[dict[str, object], ...], tuple[dict[str, object], ...]
]:
    result = evaluation()
    report = build_range_evaluation_report(
        load_range_evaluation_report_config(ROOT / "config/range_reclaim.phase7h.v1.yaml"),
        result,
    )
    report_payload = json.loads(canonical_json(report))
    assignments = tuple(json.loads(canonical_json(item)) for item in result.assignments)
    summaries = tuple(json.loads(canonical_json(item)) for item in result.summaries)
    assert isinstance(report_payload, dict)
    assert all(isinstance(item, dict) for item in (*assignments, *summaries))
    return report_payload, assignments, summaries


def test_bundle_is_deterministic_relocatable_and_independently_verified(tmp_path: Path) -> None:
    config = load_range_evidence_bundle_config(ROOT / "config/range_reclaim.phase7k.v1.yaml")
    report, assignments, summaries = evidence()
    first_path = tmp_path / "first.zip"
    second_path = tmp_path / "relocated.zip"
    first = write_range_evidence_bundle(
        output=first_path,
        report=report,
        assignments=tuple(reversed(assignments)),
        summaries=tuple(reversed(summaries)),
        config=config,
    )
    second = write_range_evidence_bundle(
        output=second_path,
        report=report,
        assignments=assignments,
        summaries=summaries,
        config=config,
    )
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first.bundle_id == second.bundle_id
    assert first.bundle_export_id != second.bundle_export_id
    verification = verify_range_evidence_bundle(second_path, config)
    assert verification.bundle_id == first.bundle_id
    assert verification.assignment_count == len(assignments)
    assert verification.summary_count == len(summaries)
    assert verification.verified and not verification.signed


def test_bundle_tampering_fails_closed(tmp_path: Path) -> None:
    config = load_range_evidence_bundle_config(ROOT / "config/range_reclaim.phase7k.v1.yaml")
    report, assignments, summaries = evidence()
    source = tmp_path / "source.zip"
    write_range_evidence_bundle(
        output=source,
        report=report,
        assignments=assignments,
        summaries=summaries,
        config=config,
    )
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(tampered, "w") as changed:
        for item in original.infolist():
            content = original.read(item)
            if item.filename == "report/report.json":
                content += b" "
            changed.writestr(item, content)
    with pytest.raises(ValueError, match="Phase 7K"):
        verify_range_evidence_bundle(tampered, config)


def test_phase7k_config_cannot_expand_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7k.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["signature_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeEvidenceBundleConfigError, match="unsigned and local"):
        load_range_evidence_bundle_config(unsafe)
