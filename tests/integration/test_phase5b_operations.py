from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.operations import (
    HealthObservation,
    HealthStatus,
    OperationalMode,
    OperationsMonitorEngine,
    OperationsRegistry,
    ScheduleDefinition,
    load_operations_monitor_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5b.v1.yaml"
COMPONENTS = (
    "CORE_RESEARCH",
    "RESEARCH_EVALUATION",
    "MODELING",
    "PAPER",
    "WEBULL_SANDBOX",
    "PORTFOLIO",
    "OPTIONS",
)


def test_phase5b_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    config = load_operations_monitor_config(CONFIG)
    as_of = datetime(2026, 8, 30, 16, tzinfo=UTC)
    schedule = ScheduleDefinition.create(
        name="paper-hourly",
        component="PAPER",
        mode=OperationalMode.SHADOW,
        first_due_at=as_of - timedelta(hours=2, minutes=10),
        cadence_seconds=3600,
        config_hash=config.config_hash,
    )
    health = tuple(
        HealthObservation.create(
            component=component,
            observed_at=as_of,
            status=HealthStatus.HEALTHY,
            reasons=(),
            evidence_fingerprint=f"sha256:{component.lower()}",
            config_hash=config.config_hash,
        )
        for component in COMPONENTS
    )
    report, plan, alerts = OperationsMonitorEngine(config).evaluate(
        as_of=as_of,
        schedules=(schedule,),
        cursors=(),
        health=health,
        source_revision="sha256:restart",
    )
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        assert registry.insert_schedule(schedule)
        assert registry.insert_schedule_plan(plan)
        for observation in health:
            assert registry.insert_health(observation)
        for alert in alerts:
            assert registry.insert_alert(alert)
        assert registry.insert_monitor_report(report)
        assert not registry.insert_schedule(schedule)
        assert not registry.insert_schedule_plan(plan)
        assert not registry.insert_monitor_report(report)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        payload, status, alert_count = registry.monitor_status(report.report_id)
        assert report.report_id in payload
        assert status == "ATTENTION"
        assert alert_count == 1
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_monitor_report(
                replace(report, source_revision="sha256:conflicting")
            )


def test_phase5b_migration_copies_are_identical() -> None:
    root_copy = ROOT / "migrations" / "023_phase_5b_monitoring.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "023_phase_5b_monitoring.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
