from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogIncidentNotificationExportIncidentEventType,
    ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError,
    ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent,
    ReviewedRangeCatalogIncidentNotificationExportIncidentState,
    load_reviewed_range_catalog_incident_notification_export_incident_notification_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7w_configuration_rejects_delivery_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7w.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["delivery_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError,
        match="disabled",
    ):
        load_reviewed_range_catalog_incident_notification_export_incident_notification_config(
            unsafe
        )


def test_phase7w_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7w.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["webhook"] = "https://invalid.example"
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationConfigError,
        match="keys",
    ):
        load_reviewed_range_catalog_incident_notification_export_incident_notification_config(
            unsafe
        )


def test_phase7w_intent_rejects_delivery_attempt() -> None:
    with pytest.raises(ValueError, match="invalid"):
        ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationIntent(
            "intent", "incident", "event", "export", "verification",
            datetime(2026, 9, 5, tzinfo=UTC),
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.OPENED,
            ReviewedRangeCatalogIncidentNotificationExportIncidentState.OPEN,
            "LOCAL_OPERATOR_OUTBOX", 1, "sha256:config", delivery_attempted=True,
        )


def test_phase7w_migrations_match() -> None:
    root = ROOT / "migrations/074_phase_7w_incident_notification_export_incident_intents.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "074_phase_7w_incident_notification_export_incident_intents.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
