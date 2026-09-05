from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogIncidentNotificationExportAuditConfigError,
    load_reviewed_range_catalog_incident_notification_export_audit_config,
)

ROOT = Path(__file__).parents[2]


def test_phase7u_configuration_rejects_delivery_authority(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7u.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["delivery_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportAuditConfigError, match="disabled"
    ):
        load_reviewed_range_catalog_incident_notification_export_audit_config(unsafe)


def test_phase7u_configuration_rejects_unknown_keys(tmp_path: Path) -> None:
    source = ROOT / "config/range_reclaim.phase7u.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["delivery_endpoint"] = "https://example.invalid"
    unsafe = tmp_path / "expanded.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        ReviewedRangeCatalogIncidentNotificationExportAuditConfigError, match="keys"
    ):
        load_reviewed_range_catalog_incident_notification_export_audit_config(unsafe)


def test_phase7u_migrations_match() -> None:
    root = ROOT / "migrations/072_phase_7u_incident_notification_export_verifications.sql"
    packaged = ROOT / (
        "src/trading_system/persistence/migrations/"
        "072_phase_7u_incident_notification_export_verifications.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
