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
    OperationsRunnerRegistry,
    ScheduleDefinition,
    load_operations_monitor_config,
    load_operations_runner_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
MONITOR_CONFIG = ROOT / "config" / "operations.phase5b.v1.yaml"
RUNNER_CONFIG = ROOT / "config" / "operations.phase5c.v1.yaml"
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


def _local_config(tmp_path: Path) -> Path:
    raw = json.loads(RUNNER_CONFIG.read_text(encoding="utf-8"))
    raw["worker"]["workspace_root"] = "."
    path = tmp_path / "runner.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _seed_due_plan(database: Path) -> tuple[str, str, datetime]:
    config = load_operations_monitor_config(MONITOR_CONFIG)
    schedule = ScheduleDefinition.create(
        name="phase5c-cli",
        component="CORE_RESEARCH",
        mode=OperationalMode.OFFLINE,
        first_due_at=AS_OF - timedelta(minutes=5),
        cadence_seconds=3600,
        config_hash=config.config_hash,
    )
    health = tuple(
        HealthObservation.create(
            component=component,
            observed_at=AS_OF,
            status=HealthStatus.HEALTHY,
            reasons=(),
            evidence_fingerprint=f"sha256:{component.lower()}",
            config_hash=config.config_hash,
        )
        for component in COMPONENTS
    )
    _, plan, _ = OperationsMonitorEngine(config).evaluate(
        as_of=AS_OF,
        schedules=(schedule,),
        cursors=(),
        health=health,
        source_revision="sha256:phase5c-cli-plan",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        registry.insert_schedule(schedule)
        registry.insert_schedule_plan(plan)
    return schedule.job_id, plan.plan_id, plan.due_jobs[0].due_at


def test_phase5c_cli_runs_only_packaged_worker_and_recovers_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    config_path = _local_config(tmp_path)
    job_id, plan_id, due_at = _seed_due_plan(database)
    source = tmp_path / "run.json"
    source.write_text(
        json.dumps(
            {
                "schedule_plan_id": plan_id,
                "schedule_job_id": job_id,
                "due_at": due_at.isoformat(),
                "requested_at": AS_OF.isoformat(),
                "action": "SQLITE_QUICK_CHECK",
                "target": database.name,
                "source_revision": "sha256:phase5c-cli",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "run-job",
                "--config",
                str(config_path),
                "--input",
                str(source),
                "--database",
                str(database),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["attempt"]["status"] == "SUCCEEDED"
    assert output["attempt"]["result"]["quick_check"] == ["ok"]
    assert output["shell_used"] is False
    assert output["network_used"] is False
    assert output["broker_write_performed"] is False
    request_id = output["request"]["request_id"]
    assert (
        main(
            [
                "operations",
                "run-status",
                "--database",
                str(database),
                "--request-id",
                request_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["attempt_count"] == 1
    assert status["attempts"][0]["status"] == "SUCCEEDED"


def test_phase5c_registry_restart_and_migration_copies(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    config_path = _local_config(tmp_path)
    job_id, plan_id, due_at = _seed_due_plan(database)
    config = load_operations_runner_config(config_path)
    source = tmp_path / "run.json"
    source.write_text(
        json.dumps(
            {
                "schedule_plan_id": plan_id,
                "schedule_job_id": job_id,
                "due_at": due_at.isoformat(),
                "requested_at": AS_OF.isoformat(),
                "action": "EVIDENCE_NOOP",
                "target": None,
                "source_revision": "sha256:restart",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "run-job",
            "--config",
            str(config_path),
            "--input",
            str(source),
            "--database",
            str(database),
        ]
    ) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        rows = repository.connection.execute(
            "SELECT request_id FROM operations_run_requests WHERE config_hash = ?",
            (config.config_hash,),
        ).fetchall()
        assert len(rows) == 1
        _, attempts = OperationsRunnerRegistry(repository).status(str(rows[0][0]))
        assert len(attempts) == 1
    root_copy = ROOT / "migrations" / "024_phase_5c_runner.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "024_phase_5c_runner.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
