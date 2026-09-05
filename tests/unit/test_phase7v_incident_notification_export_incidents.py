from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError,
    ReviewedRangeCatalogIncidentNotificationExportIncidentEvent,
    ReviewedRangeCatalogIncidentNotificationExportIncidentEventType,
    ReviewedRangeCatalogIncidentNotificationExportIncidentState,
    load_reviewed_range_catalog_incident_notification_export_incident_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7v_configuration_rejects_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7v.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["notification_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError, match="disabled"
    ):
        load_reviewed_range_catalog_incident_notification_export_incident_config(unsafe)


def test_phase7v_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7v.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["automatic_resolution"] = True
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportIncidentConfigError, match="keys"
    ):
        load_reviewed_range_catalog_incident_notification_export_incident_config(unsafe)


def test_phase7v_event_rejects_claimed_authority() -> None:
    with pytest.raises(ValueError, match="invalid"):
        ReviewedRangeCatalogIncidentNotificationExportIncidentEvent(
            "event", "incident", "export", "verification",
            datetime(2026, 9, 5, tzinfo=UTC),
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.OPENED,
            None,
            ReviewedRangeCatalogIncidentNotificationExportIncidentState.OPEN,
            "operator", "", "sha256:config", notification_sent=True,
        )


def test_phase7v_migrations_match() -> None:
    root = ROOT / "migrations/073_phase_7v_incident_notification_export_incidents.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "073_phase_7v_incident_notification_export_incidents.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
