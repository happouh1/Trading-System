from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogIncidentNotificationExportConfigError,
    load_reviewed_range_catalog_incident_notification_export_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7t_configuration_rejects_delivery_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7t.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportConfigError, match="disabled"
    ):
        load_reviewed_range_catalog_incident_notification_export_config(unsafe)


def test_phase7t_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7t.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["destination"] = "external"
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportConfigError, match="keys"
    ):
        load_reviewed_range_catalog_incident_notification_export_config(unsafe)


def test_phase7t_migrations_match() -> None:
    root = ROOT / "migrations/071_phase_7t_incident_notification_exports.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "071_phase_7t_incident_notification_exports.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
