from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from trading_system.reporting import (
    ReviewedRangeCatalogIncidentNotificationExportIncidentEventType,
    ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary,
)
from trading_system.research.range_terminal_boundary import (
    RangeTerminalBoundaryConfigError,
    assess_range_terminal_boundary,
    load_range_terminal_boundary_config,
)

CONFIG = Path("config/range_reclaim.phase7x.v1.yaml")


def source_summary() -> ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary:
    return ReviewedRangeCatalogIncidentNotificationExportIncidentNotificationSummary(
        "incident-1",
        "notification-export-1",
        3,
        (
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.OPENED,
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.ACKNOWLEDGED,
            ReviewedRangeCatalogIncidentNotificationExportIncidentEventType.RESOLVED,
        ),
        0,
    )


def test_assessment_is_deterministic_minimal_and_non_authoritative() -> None:
    config = load_range_terminal_boundary_config(CONFIG)
    first = assess_range_terminal_boundary(config, source_summary())
    second = assess_range_terminal_boundary(config, source_summary())
    assert first == second
    assert first.intent_count == 3
    assert first.route == "LOCAL_OPERATOR_OUTBOX"
    assert first.terminal_boundary
    assert not first.network_used
    assert not first.delivery_attempted
    assert not first.artifact_exported
    assert not first.incident_created
    assert not first.approval_granted
    assert not first.promotion_authority
    assert not first.broker_write_performed


def test_source_must_be_complete_and_never_delivered() -> None:
    config = load_range_terminal_boundary_config(CONFIG)
    summary = source_summary()
    with pytest.raises(ValueError, match="empty or incomplete"):
        assess_range_terminal_boundary(config, replace(summary, intent_count=4))
    with pytest.raises(ValueError, match="crossed the offline delivery boundary"):
        assess_range_terminal_boundary(config, replace(summary, delivery_attempt_count=1))


def test_configuration_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["network_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeTerminalBoundaryConfigError, match="authority"):
        load_range_terminal_boundary_config(path)
