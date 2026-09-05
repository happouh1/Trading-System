from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogConfigError,
    load_reviewed_range_catalog_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7o_configuration_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7o.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["promotion_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogConfigError, match="disabled"):
        load_reviewed_range_catalog_config(unsafe)


def test_phase7o_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7o.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["minimum_catalog_size"] = 10
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogConfigError, match="keys"):
        load_reviewed_range_catalog_config(unsafe)


def test_phase7o_migrations_match() -> None:
    root = ROOT / "migrations/066_phase_7o_reviewed_bundle_catalogs.sql"
    packaged = (
        ROOT
        / "src/trading_system/persistence/migrations/066_phase_7o_reviewed_bundle_catalogs.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
