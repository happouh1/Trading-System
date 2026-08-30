from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.operations import (
    AlertKind,
    HealthObservation,
    HealthStatus,
    MonitorStatus,
    OperationalMode,
    OperationsMonitorConfigError,
    OperationsMonitorEngine,
    ScheduleCursor,
    ScheduleDefinition,
    load_operations_monitor_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5b.v1.yaml"
AS_OF = datetime(2026, 8, 30, 16, tzinfo=UTC)
COMPONENTS = (
    "CORE_RESEARCH",
    "RESEARCH_EVALUATION",
    "MODELING",
    "PAPER",
    "WEBULL_SANDBOX",
    "PORTFOLIO",
    "OPTIONS",
)


def _health(
    *,
    observed_at: datetime = AS_OF,
    status_by_component: dict[str, HealthStatus] | None = None,
) -> tuple[HealthObservation, ...]:
    config = load_operations_monitor_config(CONFIG)
    overrides = status_by_component or {}
    return tuple(
        HealthObservation.create(
            component=component,
            observed_at=observed_at,
            status=overrides.get(component, HealthStatus.HEALTHY),
            reasons=("FIXTURE_FAILURE",)
            if overrides.get(component, HealthStatus.HEALTHY) is not HealthStatus.HEALTHY
            else (),
            evidence_fingerprint=f"sha256:{component.lower()}",
            config_hash=config.config_hash,
        )
        for component in COMPONENTS
    )


def _schedule(*, first_due_at: datetime, cadence_seconds: int = 3600) -> ScheduleDefinition:
    config = load_operations_monitor_config(CONFIG)
    return ScheduleDefinition.create(
        name="core-hourly",
        component="CORE_RESEARCH",
        mode=OperationalMode.OFFLINE,
        first_due_at=first_due_at,
        cadence_seconds=cadence_seconds,
        config_hash=config.config_hash,
    )


def test_phase5b_config_locks_nonexecuting_authority(tmp_path: Path) -> None:
    config = load_operations_monitor_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["process_execution_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsMonitorConfigError, match="offline/shadow-only"):
        load_operations_monitor_config(invalid)


def test_due_plan_uses_completed_boundaries_and_is_order_independent() -> None:
    config = load_operations_monitor_config(CONFIG)
    first = _schedule(first_due_at=AS_OF - timedelta(hours=2, minutes=20))
    second = ScheduleDefinition.create(
        name="paper-daily",
        component="PAPER",
        mode=OperationalMode.SHADOW,
        first_due_at=AS_OF + timedelta(hours=1),
        cadence_seconds=86400,
        config_hash=config.config_hash,
    )
    engine = OperationsMonitorEngine(config)
    report, plan, alerts = engine.evaluate(
        as_of=AS_OF,
        schedules=(first, second),
        cursors=(),
        health=_health(),
        source_revision="sha256:phase5b-fixture",
    )
    reverse_report, reverse_plan, reverse_alerts = engine.evaluate(
        as_of=AS_OF,
        schedules=(second, first),
        cursors=(),
        health=tuple(reversed(_health())),
        source_revision="sha256:phase5b-fixture",
    )
    assert (report, plan, alerts) == (reverse_report, reverse_plan, reverse_alerts)
    assert plan.due_jobs[0].due_at == AS_OF - timedelta(minutes=20)
    assert plan.due_jobs[0].overdue_seconds == 1200
    assert plan.next_due == tuple(sorted(plan.next_due))
    assert report.status is MonitorStatus.ATTENTION
    assert {item.kind for item in alerts} == {AlertKind.SCHEDULE_OVERDUE}


def test_completed_boundary_prevents_due_and_exact_grace_does_not_alert() -> None:
    config = load_operations_monitor_config(CONFIG)
    schedule = _schedule(first_due_at=AS_OF - timedelta(seconds=300))
    engine = OperationsMonitorEngine(config)
    report, plan, alerts = engine.evaluate(
        as_of=AS_OF,
        schedules=(schedule,),
        cursors=(ScheduleCursor(schedule.job_id, schedule.first_due_at),),
        health=_health(),
        source_revision="sha256:complete",
    )
    assert report.status is MonitorStatus.HEALTHY
    assert not plan.due_jobs
    assert not alerts
    _, due_plan, exact_alerts = engine.evaluate(
        as_of=AS_OF,
        schedules=(schedule,),
        cursors=(),
        health=_health(),
        source_revision="sha256:grace",
    )
    assert due_plan.due_jobs[0].overdue_seconds == 300
    assert not exact_alerts


def test_health_alerts_are_stale_and_status_specific() -> None:
    config = load_operations_monitor_config(CONFIG)
    schedule = _schedule(first_due_at=AS_OF + timedelta(hours=1))
    health = _health(
        observed_at=AS_OF - timedelta(seconds=901),
        status_by_component={
            "PAPER": HealthStatus.DEGRADED,
            "WEBULL_SANDBOX": HealthStatus.FAILED,
        },
    )
    report, _, alerts = OperationsMonitorEngine(config).evaluate(
        as_of=AS_OF,
        schedules=(schedule,),
        cursors=(),
        health=health,
        source_revision="sha256:health",
    )
    kinds = [item.kind for item in alerts]
    assert kinds.count(AlertKind.HEALTH_STALE) == 7
    assert AlertKind.COMPONENT_DEGRADED in kinds
    assert AlertKind.COMPONENT_FAILED in kinds
    assert report.status is MonitorStatus.ATTENTION


def test_monitor_rejects_future_or_incomplete_evidence() -> None:
    config = load_operations_monitor_config(CONFIG)
    schedule = _schedule(first_due_at=AS_OF)
    engine = OperationsMonitorEngine(config)
    with pytest.raises(ValueError, match="exactly all"):
        engine.evaluate(
            as_of=AS_OF,
            schedules=(schedule,),
            cursors=(),
            health=_health()[:-1],
            source_revision="sha256:missing",
        )
    with pytest.raises(ValueError, match="future health"):
        engine.evaluate(
            as_of=AS_OF,
            schedules=(schedule,),
            cursors=(),
            health=tuple(
                replace(item, observed_at=AS_OF + timedelta(seconds=1)) for item in _health()
            ),
            source_revision="sha256:future-health",
        )
    with pytest.raises(ValueError, match="future schedule"):
        engine.evaluate(
            as_of=AS_OF,
            schedules=(schedule,),
            cursors=(ScheduleCursor(schedule.job_id, AS_OF + timedelta(seconds=1)),),
            health=_health(),
            source_revision="sha256:future-cursor",
        )


def test_phase5b_cli_is_offline_and_persists_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "monitor.json"
    database = tmp_path / "operations.sqlite"
    source.write_text(
        json.dumps(
            {
                "as_of": AS_OF.isoformat(),
                "source_revision": "sha256:cli",
                "jobs": [
                    {
                        "name": "paper-hourly",
                        "component": "PAPER",
                        "mode": "SHADOW",
                        "first_due_at": (AS_OF - timedelta(hours=2)).isoformat(),
                        "cadence_seconds": 3600,
                        "last_completed_at": None,
                    }
                ],
                "health": [
                    {
                        "component": component,
                        "observed_at": AS_OF.isoformat(),
                        "status": "HEALTHY",
                        "reasons": [],
                        "evidence_fingerprint": f"sha256:{component.lower()}",
                    }
                    for component in COMPONENTS
                ],
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "monitor",
                "--config",
                str(CONFIG),
                "--input",
                str(source),
                "--database",
                str(database),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    report_id = output["report"]["report_id"]
    assert output["report"]["status"] == "ATTENTION"
    assert "NO_NETWORK_CREDENTIAL_OR_BROKER_AUTHORITY" in output["report"]["disclosures"]
    assert (
        main(
            [
                "operations",
                "monitor-status",
                "--database",
                str(database),
                "--report-id",
                report_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "ATTENTION"
    assert status["alert_count"] == 0


def test_phase5b_cli_rejects_nonstring_job_identity(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    source.write_text(
        json.dumps(
            {
                "as_of": AS_OF.isoformat(),
                "source_revision": "sha256:invalid",
                "jobs": [
                    {
                        "name": None,
                        "component": "PAPER",
                        "mode": "SHADOW",
                        "first_due_at": AS_OF.isoformat(),
                        "cadence_seconds": 3600,
                        "last_completed_at": None,
                    }
                ],
                "health": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="job name"):
        main(
            [
                "operations",
                "monitor",
                "--config",
                str(CONFIG),
                "--input",
                str(source),
                "--database",
                str(tmp_path / "operations.sqlite"),
            ]
        )
