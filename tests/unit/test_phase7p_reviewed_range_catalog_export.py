from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalog,
    ReviewedRangeCatalogEntry,
    ReviewedRangeCatalogExportConfigError,
    load_reviewed_range_catalog_export_config,
    write_reviewed_range_catalog_manifest,
)

ROOT = Path(__file__).parents[2]


def catalog() -> ReviewedRangeCatalog:
    verified_at = datetime(2026, 9, 5, 15, tzinfo=UTC)
    entry = ReviewedRangeCatalogEntry(
        "reviewed-export-1", "reviewed-bundle-1", "verification-1", "sha256:artifact",
        "sha256:reviews", 1, verified_at, "sha256:export", "sha256:verification",
    )
    return ReviewedRangeCatalog(
        "catalog-1", "fixture-catalog", datetime(2026, 9, 5, 16, tzinfo=UTC), (entry,),
        "sha256:catalog", 1, "fixture-revision", "sha256:config",
    )


def test_phase7p_export_is_atomic_deterministic_and_content_bound(tmp_path: Path) -> None:
    config = load_reviewed_range_catalog_export_config(
        ROOT / "config/range_reclaim.phase7p.v1.yaml"
    )
    output = tmp_path / "catalog.json"
    first = write_reviewed_range_catalog_manifest(
        catalog=catalog(), output=output, config=config
    )
    second = write_reviewed_range_catalog_manifest(
        catalog=catalog(), output=output, config=config
    )
    assert first == second
    assert first.byte_count == len(output.read_bytes())
    assert first.content_hash.startswith("sha256:")
    assert output.read_bytes().endswith(b"\n")
    assert not tuple(tmp_path.glob(".reviewed-range-catalog-*.tmp"))


def test_phase7p_configuration_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7p.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["ranking_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogExportConfigError, match="disabled"):
        load_reviewed_range_catalog_export_config(unsafe)


def test_phase7p_export_requires_existing_parent(tmp_path: Path) -> None:
    config = load_reviewed_range_catalog_export_config(
        ROOT / "config/range_reclaim.phase7p.v1.yaml"
    )
    with pytest.raises(ValueError, match="parent"):
        write_reviewed_range_catalog_manifest(
            catalog=catalog(), output=tmp_path / "missing" / "catalog.json", config=config
        )


def test_phase7p_migrations_match() -> None:
    root = ROOT / "migrations/067_phase_7p_reviewed_catalog_exports.sql"
    packaged = (
        ROOT / "src/trading_system/persistence/migrations/067_phase_7p_reviewed_catalog_exports.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
