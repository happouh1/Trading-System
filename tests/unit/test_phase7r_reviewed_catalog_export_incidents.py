from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogExportIncidentConfigError,
    ReviewedRangeCatalogExportIncidentEvent,
    ReviewedRangeCatalogExportIncidentEventType,
    ReviewedRangeCatalogExportIncidentState,
    load_reviewed_range_catalog_export_incident_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7r_configuration_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7r.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["notification_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogExportIncidentConfigError, match="disabled"):
        load_reviewed_range_catalog_export_incident_config(unsafe)


def test_phase7r_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7r.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["automatic_resolution"] = True
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogExportIncidentConfigError, match="keys"):
        load_reviewed_range_catalog_export_incident_config(unsafe)


def test_phase7r_event_rejects_claimed_authority() -> None:
    with pytest.raises(ValueError, match="invalid"):
        ReviewedRangeCatalogExportIncidentEvent(
            "event", "incident", "export", "verification",
            datetime(2026, 9, 5, tzinfo=UTC),
            ReviewedRangeCatalogExportIncidentEventType.OPENED,
            None,
            ReviewedRangeCatalogExportIncidentState.OPEN,
            "operator", "", "sha256:config", promotion_authority=True,
        )


def test_phase7r_migrations_match() -> None:
    root = ROOT / "migrations/069_phase_7r_reviewed_catalog_export_incidents.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "069_phase_7r_reviewed_catalog_export_incidents.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
