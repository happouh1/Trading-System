from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.test_phase7k_range_evidence_bundle import evidence
from trading_system.reporting import (
    RangeBundleReviewAssertion,
    RangeBundleReviewConfig,
    RangeBundleReviewConfigError,
    RangeBundleReviewVerdict,
    RangeEvidenceBundleVerification,
    build_range_bundle_review,
    load_range_bundle_review_config,
    load_range_evidence_bundle_config,
    verify_range_evidence_bundle,
    write_range_evidence_bundle,
)

ROOT = Path(__file__).parents[2]


def verification(tmp_path: Path) -> RangeEvidenceBundleVerification:
    report, assignments, summaries = evidence()
    path = tmp_path / "evidence.zip"
    write_range_evidence_bundle(
        output=path,
        report=report,
        assignments=assignments,
        summaries=summaries,
        config=load_range_evidence_bundle_config(
            ROOT / "config/range_reclaim.phase7k.v1.yaml"
        ),
    )
    return verify_range_evidence_bundle(
        path, load_range_evidence_bundle_config(ROOT / "config/range_reclaim.phase7k.v1.yaml")
    )


def test_review_is_deterministic_and_normalizes_reason_order(tmp_path: Path) -> None:
    verified = verification(tmp_path)
    config = load_range_bundle_review_config(ROOT / "config/range_reclaim.phase7l.v1.yaml")
    first = _review(verified, config, ("SCHEMAS_READABLE", "ROOTS_MATCH"))
    second = _review(verified, config, ("ROOTS_MATCH", "SCHEMAS_READABLE", "ROOTS_MATCH"))
    assert first == second
    assert first.reason_codes == ("ROOTS_MATCH", "SCHEMAS_READABLE")
    assert not first.reviewer_identity_authenticated
    assert not first.eligible_for_approval
    assert not first.eligible_for_promotion


def test_review_validation_fails_closed(tmp_path: Path) -> None:
    verified = verification(tmp_path)
    config = load_range_bundle_review_config(ROOT / "config/range_reclaim.phase7l.v1.yaml")
    with pytest.raises(ValueError, match="reviewer_id"):
        build_range_bundle_review(
            verification=verified,
            bundle_export_id="export",
            reviewer_id="bad reviewer",
            reviewed_at=datetime.now(UTC),
            verdict=RangeBundleReviewVerdict.UNCERTAIN_CONTENT_INTEGRITY,
            reason_codes=(),
            notes="",
            config=config,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_range_bundle_review(
            verification=verified,
            bundle_export_id="export",
            reviewer_id="reviewer",
            reviewed_at=datetime(2026, 9, 4),
            verdict=RangeBundleReviewVerdict.UNCERTAIN_CONTENT_INTEGRITY,
            reason_codes=(),
            notes="",
            config=config,
        )


def test_phase7l_config_cannot_expand_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7l.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["approval_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeBundleReviewConfigError, match="entirely disabled"):
        load_range_bundle_review_config(unsafe)


def _review(
    verified: RangeEvidenceBundleVerification,
    config: RangeBundleReviewConfig,
    reasons: tuple[str, ...],
) -> RangeBundleReviewAssertion:
    return build_range_bundle_review(
        verification=verified,
        bundle_export_id="range_evidence_bundle_export_example",
        reviewer_id="reviewer.one",
        reviewed_at=datetime(2026, 9, 4, 14, 30, tzinfo=UTC),
        verdict=RangeBundleReviewVerdict.CONFIRMED_CONTENT_INTEGRITY,
        reason_codes=reasons,
        notes="Bundle members match the recorded review checklist.",
        config=config,
    )
