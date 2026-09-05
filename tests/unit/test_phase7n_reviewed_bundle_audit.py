from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeBundleAuditConfigError,
    load_reviewed_range_bundle_audit_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7n_configuration_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7n.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["approval_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeBundleAuditConfigError, match="disabled"):
        load_reviewed_range_bundle_audit_config(unsafe)


def test_phase7n_migrations_match() -> None:
    root = ROOT / "migrations/065_phase_7n_reviewed_bundle_verifications.sql"
    packaged = (
        ROOT
        / "src/trading_system/persistence/migrations/065_phase_7n_reviewed_bundle_verifications.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
