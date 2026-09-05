from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogExportIncidentEventType,
    ReviewedRangeCatalogExportIncidentState,
    ReviewedRangeCatalogIncidentNotificationConfigError,
    ReviewedRangeCatalogIncidentNotificationIntent,
    load_reviewed_range_catalog_incident_notification_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7s_configuration_rejects_delivery_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7s.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["delivery_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogIncidentNotificationConfigError, match="disabled"):
        load_reviewed_range_catalog_incident_notification_config(unsafe)


def test_phase7s_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7s.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["webhook"] = "https://invalid.example"
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReviewedRangeCatalogIncidentNotificationConfigError, match="keys"):
        load_reviewed_range_catalog_incident_notification_config(unsafe)


def test_phase7s_intent_rejects_delivery_attempt() -> None:
    with pytest.raises(ValueError, match="invalid"):
        ReviewedRangeCatalogIncidentNotificationIntent(
            "intent", "incident", "event", "export", "verification",
            datetime(2026, 9, 5, tzinfo=UTC),
            ReviewedRangeCatalogExportIncidentEventType.OPENED,
            ReviewedRangeCatalogExportIncidentState.OPEN,
            "LOCAL_OPERATOR_OUTBOX", 1, "sha256:config", delivery_attempted=True,
        )


def test_phase7s_migrations_match() -> None:
    root = ROOT / "migrations/070_phase_7s_reviewed_catalog_incident_notification_intents.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "070_phase_7s_reviewed_catalog_incident_notification_intents.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
