from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogExportAuditConfigError,
    load_reviewed_range_catalog_export_audit_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7q_configuration_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7q.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["approval_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogExportAuditConfigError, match="disabled"):
        load_reviewed_range_catalog_export_audit_config(unsafe)


def test_phase7q_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7q.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["schedule"] = "hourly"
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogExportAuditConfigError, match="keys"):
        load_reviewed_range_catalog_export_audit_config(unsafe)


def test_phase7q_migrations_match() -> None:
    root = ROOT / "migrations/068_phase_7q_reviewed_catalog_export_verifications.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "068_phase_7q_reviewed_catalog_export_verifications.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
