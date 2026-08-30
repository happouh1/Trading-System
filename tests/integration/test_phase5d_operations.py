from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.cli.main import main
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
MONITOR_CONFIG = ROOT / "config" / "operations.phase5b.v1.yaml"
RUNNER_CONFIG = ROOT / "config" / "operations.phase5c.v1.yaml"
CONTROL_CONFIG = ROOT / "config" / "operations.phase5d.v1.yaml"
COMPONENTS = (
    "CORE_RESEARCH",
    "RESEARCH_EVALUATION",
    "MODELING",
    "PAPER",
    "WEBULL_SANDBOX",
    "PORTFOLIO",
    "OPTIONS",
)


def test_phase5d_migration_and_restart_tables(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        tables = {
            str(row[0])
            for row in repository.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "operations_approval_events",
        "operations_kill_switch_events",
        "operations_cancellation_events",
        "operations_incident_events",
        "operations_control_snapshots",
    }.issubset(tables)
    root_copy = ROOT / "migrations" / "025_phase_5d_controls.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "025_phase_5d_controls.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()


def test_phase5d_cli_governed_run_is_halted_then_authorized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    database = tmp_path / "operations.sqlite"
    monitor_config = load_operations_monitor_config(MONITOR_CONFIG)
    schedule = ScheduleDefinition.create(
        name="phase5d-cli",
        component="CORE_RESEARCH",
        mode=OperationalMode.OFFLINE,
        first_due_at=now - timedelta(seconds=1),
        cadence_seconds=3600,
        config_hash=monitor_config.config_hash,
    )
    health = tuple(
        HealthObservation.create(
            component=component,
            observed_at=now,
            status=HealthStatus.HEALTHY,
            reasons=(),
            evidence_fingerprint=f"sha256:{component.lower()}",
            config_hash=monitor_config.config_hash,
        )
        for component in COMPONENTS
    )
    _, plan, _ = OperationsMonitorEngine(monitor_config).evaluate(
        as_of=now,
        schedules=(schedule,),
        cursors=(),
        health=health,
        source_revision="sha256:phase5d-cli-plan",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        operations = OperationsRegistry(repository)
        operations.insert_schedule(schedule)
        operations.insert_schedule_plan(plan)
    run_input = tmp_path / "run.json"
    run_input.write_text(
        json.dumps(
            {
                "schedule_plan_id": plan.plan_id,
                "schedule_job_id": schedule.job_id,
                "due_at": plan.due_jobs[0].due_at.isoformat(),
                "requested_at": now.isoformat(),
                "action": "EVIDENCE_NOOP",
                "target": None,
                "source_revision": "sha256:phase5d-cli-run",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "prepare-run",
            "--runner-config",
            str(RUNNER_CONFIG),
            "--input",
            str(run_input),
            "--database",
            str(database),
        ]
    ) == 0
    prepared = json.loads(capsys.readouterr().out)
    request_id = str(prepared["request"]["request_id"])
    assert prepared["worker_invoked"] is False
    assert main(
        [
            "operations",
            "control-status",
            "--config",
            str(CONTROL_CONFIG),
            "--database",
            str(database),
            "--as-of",
            now.isoformat(),
            "--request-id",
            request_id,
        ]
    ) == 0
    halted = json.loads(capsys.readouterr().out)
    assert halted["snapshot"]["status"] == "HALTED"
    assert halted["remote_control_used"] is False
    approval_input = tmp_path / "approval.json"
    approval_input.write_text(
        json.dumps(
            {
                "request_id": request_id,
                "operator_id": "operator-a",
                "action": "GRANT",
                "known_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "reasons": ["APPROVED_OFFLINE_NOOP"],
            }
        ),
        encoding="utf-8",
    )
    release_input = tmp_path / "release.json"
    release_input.write_text(
        json.dumps(
            {
                "component": None,
                "operator_id": "operator-a",
                "action": "RELEASE",
                "known_at": now.isoformat(),
                "reasons": ["REVIEWED_OFFLINE_NOOP"],
            }
        ),
        encoding="utf-8",
    )
    for command, source in (("approval", approval_input), ("kill-switch", release_input)):
        assert main(
            [
                "operations",
                command,
                "--config",
                str(CONTROL_CONFIG),
                "--input",
                str(source),
                "--database",
                str(database),
            ]
        ) == 0
        recorded = json.loads(capsys.readouterr().out)
        assert recorded["recorded"] is True
        assert recorded["operator_authenticated"] is False
    assert main(
        [
            "operations",
            "controlled-run",
            "--runner-config",
            str(RUNNER_CONFIG),
            "--control-config",
            str(CONTROL_CONFIG),
            "--input",
            str(run_input),
            "--database",
            str(database),
        ]
    ) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["attempt"]["status"] == "SUCCEEDED"
    assert completed["control_enforced"] is True
    assert completed["remote_control_used"] is False
    assert completed["broker_write_performed"] is False
