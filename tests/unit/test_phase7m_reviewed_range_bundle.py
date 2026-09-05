from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.test_phase7k_range_evidence_bundle import evidence
from trading_system.reporting import (
    RangeBundleReviewAssertion,
    RangeBundleReviewVerdict,
    RangeEvidenceBundleConfig,
    RangeEvidenceBundleVerification,
    ReviewedRangeBundleConfigError,
    build_range_bundle_review,
    load_range_bundle_review_config,
    load_range_evidence_bundle_config,
    load_reviewed_range_bundle_config,
    verify_range_evidence_bundle,
    verify_reviewed_range_bundle,
    write_range_evidence_bundle,
    write_reviewed_range_bundle,
)

ROOT = Path(__file__).parents[2]


def source_and_review(
    tmp_path: Path,
) -> tuple[
    Path,
    RangeEvidenceBundleConfig,
    RangeEvidenceBundleVerification,
    RangeBundleReviewAssertion,
]:
    source_config = load_range_evidence_bundle_config(
        ROOT / "config/range_reclaim.phase7k.v1.yaml"
    )
    report, assignments, summaries = evidence()
    source_path = tmp_path / "source.zip"
    source_record = write_range_evidence_bundle(
        output=source_path,
        report=report,
        assignments=assignments,
        summaries=summaries,
        config=source_config,
    )
    verified = verify_range_evidence_bundle(source_path, source_config)
    review = build_range_bundle_review(
        verification=verified,
        bundle_export_id=source_record.bundle_export_id,
        reviewer_id="reviewer",
        reviewed_at=datetime(2026, 9, 4, tzinfo=UTC),
        verdict=RangeBundleReviewVerdict.CONFIRMED_CONTENT_INTEGRITY,
        reason_codes=("ROOTS_MATCH",),
        notes="Content review only.",
        config=load_range_bundle_review_config(
            ROOT / "config/range_reclaim.phase7l.v1.yaml"
        ),
    )
    return source_path, source_config, verified, review


def test_reviewed_bundle_is_deterministic_relocatable_and_verified(tmp_path: Path) -> None:
    source_path, source_config, verified, review = source_and_review(tmp_path)
    config = load_reviewed_range_bundle_config(ROOT / "config/range_reclaim.phase7m.v1.yaml")
    first_path = tmp_path / "first.zip"
    second_path = tmp_path / "second.zip"
    first = write_reviewed_range_bundle(
        output=first_path,
        source_bundle=source_path,
        source=verified,
        reviews=(review,),
        config=config,
    )
    second = write_reviewed_range_bundle(
        output=second_path,
        source_bundle=source_path,
        source=verified,
        reviews=(review,),
        config=config,
    )
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first.reviewed_bundle_id == second.reviewed_bundle_id
    assert first.reviewed_bundle_export_id != second.reviewed_bundle_export_id
    result = verify_reviewed_range_bundle(second_path, config, source_config)
    assert result.reviewed_bundle_id == first.reviewed_bundle_id
    assert result.review_count == 1
    assert result.verified and not result.signed and not result.approval_granted


def test_reviewed_bundle_tampering_fails_closed(tmp_path: Path) -> None:
    source_path, source_config, verified, review = source_and_review(tmp_path)
    config = load_reviewed_range_bundle_config(ROOT / "config/range_reclaim.phase7m.v1.yaml")
    original = tmp_path / "original.zip"
    write_reviewed_range_bundle(
        output=original,
        source_bundle=source_path,
        source=verified,
        reviews=(review,),
        config=config,
    )
    changed = tmp_path / "changed.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(changed, "w") as target:
        for item in source.infolist():
            content = source.read(item)
            if item.filename.startswith("reviews/"):
                content += b" "
            target.writestr(item, content)
    with pytest.raises(ValueError, match="Phase 7M"):
        verify_reviewed_range_bundle(changed, config, source_config)


def test_phase7m_config_rejects_authority_and_migrations_match(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7m.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["approval_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeBundleConfigError, match="disabled"):
        load_reviewed_range_bundle_config(unsafe)
    root = ROOT / "migrations/064_phase_7m_reviewed_range_bundles.sql"
    packaged = (
        ROOT
        / "src/trading_system/persistence/migrations/064_phase_7m_reviewed_range_bundles.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
