from __future__ import annotations

import json
import sqlite3
import subprocess
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.operations import (
    AttemptStatus,
    HealthObservation,
    HealthStatus,
    JobRunRequest,
    OperationalMode,
    OperationsJobRunner,
    OperationsMonitorEngine,
    OperationsRegistry,
    OperationsRunnerConfigError,
    OperationsRunnerRegistry,
    ScheduleDefinition,
    SchedulePlan,
    WorkerAction,
    WorkerInvocation,
    load_operations_monitor_config,
    load_operations_runner_config,
)
from trading_system.operations.worker import execute
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


def _local_runner_config(tmp_path: Path) -> Path:
    raw = json.loads(RUNNER_CONFIG.read_text(encoding="utf-8"))
    raw["worker"]["workspace_root"] = "."
    path = tmp_path / "runner.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _due_plan(repository: SQLiteRepository) -> tuple[ScheduleDefinition, SchedulePlan]:
    config = load_operations_monitor_config(MONITOR_CONFIG)
    schedule = ScheduleDefinition.create(
        name="phase5c-fixture",
        component="CORE_RESEARCH",
        mode=OperationalMode.OFFLINE,
        first_due_at=AS_OF - timedelta(minutes=10),
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
        source_revision="sha256:phase5c-plan",
    )
    registry = OperationsRegistry(repository)
    registry.insert_schedule(schedule)
    registry.insert_schedule_plan(plan)
    return schedule, plan


def _request(
    runner_config_path: Path,
    schedule: ScheduleDefinition,
    plan: SchedulePlan,
    *,
    action: WorkerAction = WorkerAction.EVIDENCE_NOOP,
    target: str | None = None,
) -> JobRunRequest:
    config = load_operations_runner_config(runner_config_path)
    plan_id = plan.plan_id
    due_at = plan.due_jobs[0].due_at
    return JobRunRequest.create(
        schedule_plan_id=plan_id,
        schedule_job_id=schedule.job_id,
        due_at=due_at,
        requested_at=AS_OF,
        action=action,
        target=target,
        source_revision="sha256:phase5c-request",
        config_hash=config.config_hash,
    )


class _SuccessTransport:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request: JobRunRequest, target: Path | None) -> WorkerInvocation:
        self.calls += 1
        return WorkerInvocation(0, {"status": "OK"}, b'{"status":"OK"}', b"")


class _TimeoutTransport:
    def invoke(self, request: JobRunRequest, target: Path | None) -> WorkerInvocation:
        raise subprocess.TimeoutExpired((request.action.value,), 1)


def _clock(values: tuple[datetime, ...]) -> Iterator[datetime]:
    return iter(values)


def test_phase5c_config_locks_packaged_offline_authority(tmp_path: Path) -> None:
    config = load_operations_runner_config(RUNNER_CONFIG)
    assert config.allowed_actions == ("EVIDENCE_NOOP", "SQLITE_QUICK_CHECK")
    raw = json.loads(RUNNER_CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["shell_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsRunnerConfigError, match="packaged and offline"):
        load_operations_runner_config(invalid)


def test_request_is_deterministic_and_rejects_unsafe_targets(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    database = tmp_path / "registry.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        first = _request(config_path, schedule, plan)
        second = _request(config_path, schedule, plan)
    assert first == second
    config = load_operations_runner_config(config_path)
    with pytest.raises(ValueError, match="canonical relative"):
        JobRunRequest.create(
            schedule_plan_id="plan",
            schedule_job_id="job",
            due_at=AS_OF,
            requested_at=AS_OF,
            action=WorkerAction.SQLITE_QUICK_CHECK,
            target="../secret.sqlite",
            source_revision="sha256:unsafe",
            config_hash=config.config_hash,
        )


def test_packaged_worker_actions_are_bounded_and_read_only(tmp_path: Path) -> None:
    noop = execute(WorkerAction.EVIDENCE_NOOP, None)
    assert noop["status"] == "OK"
    database = tmp_path / "fixture.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE fixture (value TEXT NOT NULL)")
        connection.execute("INSERT INTO fixture VALUES ('unchanged')")
    before = database.read_bytes()
    result = execute(WorkerAction.SQLITE_QUICK_CHECK, database.resolve())
    assert result["quick_check"] == ("ok",)
    assert database.read_bytes() == before


def test_runner_is_idempotent_after_success(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    config = load_operations_runner_config(config_path)
    database = tmp_path / "operations.sqlite"
    transport = _SuccessTransport()
    times = _clock((AS_OF, AS_OF + timedelta(seconds=1)))
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        request = _request(config_path, schedule, plan)
        runner = OperationsJobRunner(
            config,
            OperationsRunnerRegistry(repository),
            transport=transport,
            clock=lambda: next(times),
        )
        first = runner.run_once(request)
        second = runner.run_once(request)
    assert first == second
    assert first.status is AttemptStatus.SUCCEEDED
    assert transport.calls == 1


def test_timeout_records_retry_and_enforces_eligibility(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    config = load_operations_runner_config(config_path)
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        request = _request(config_path, schedule, plan)
        registry = OperationsRunnerRegistry(repository)
        timeout_times = _clock((AS_OF, AS_OF + timedelta(seconds=1)))
        timed_out = OperationsJobRunner(
            config,
            registry,
            transport=_TimeoutTransport(),
            clock=lambda: next(timeout_times),
        ).run_once(request)
        assert timed_out.status is AttemptStatus.TIMED_OUT
        assert timed_out.next_retry_at == AS_OF + timedelta(seconds=61)
        with pytest.raises(ValueError, match="not yet eligible"):
            OperationsJobRunner(
                config,
                registry,
                transport=_SuccessTransport(),
                clock=lambda: AS_OF + timedelta(seconds=30),
            ).run_once(request)
        retry_times = _clock(
            (AS_OF + timedelta(seconds=61), AS_OF + timedelta(seconds=62))
        )
        retry = OperationsJobRunner(
            config,
            registry,
            transport=_SuccessTransport(),
            clock=lambda: next(retry_times),
        ).run_once(request)
    assert retry.status is AttemptStatus.SUCCEEDED
    assert retry.attempt_number == 2


def test_active_lease_blocks_and_expired_lease_recovers(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    config = load_operations_runner_config(config_path)
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        request = _request(config_path, schedule, plan)
        registry = OperationsRunnerRegistry(repository)
        registry.validate_due_request(request)
        registry.insert_run_request(request)
        assert registry.acquire_lease(
            schedule.job_id,
            request.request_id,
            AS_OF,
            AS_OF + timedelta(seconds=100),
        )
        with pytest.raises(ValueError, match="active runner lease"):
            OperationsJobRunner(
                config,
                registry,
                transport=_SuccessTransport(),
                clock=lambda: AS_OF + timedelta(seconds=1),
            ).run_once(request)
        recovery_times = _clock(
            (AS_OF + timedelta(seconds=101), AS_OF + timedelta(seconds=102))
        )
        recovered = OperationsJobRunner(
            config,
            registry,
            transport=_SuccessTransport(),
            clock=lambda: next(recovery_times),
        ).run_once(request)
    assert recovered.status is AttemptStatus.SUCCEEDED


def test_request_must_match_exact_due_plan_evidence(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        request = _request(config_path, schedule, plan)
        invalid = JobRunRequest.create(
            schedule_plan_id=request.schedule_plan_id,
            schedule_job_id=request.schedule_job_id,
            due_at=request.due_at + timedelta(seconds=1),
            requested_at=request.requested_at,
            action=request.action,
            target=request.target,
            source_revision=request.source_revision,
            config_hash=request.config_hash,
        )
        with pytest.raises(ValueError, match="exact due job"):
            OperationsRunnerRegistry(repository).validate_due_request(invalid)


def test_schedule_boundary_identity_prevents_redefinition(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        request = _request(config_path, schedule, plan)
        changed = replace(
            request,
            action=WorkerAction.SQLITE_QUICK_CHECK,
            target="operations.sqlite",
        )
        assert changed.request_id == request.request_id
        registry = OperationsRunnerRegistry(repository)
        assert registry.insert_run_request(request)
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_run_request(changed)


def test_future_request_cannot_run_early(tmp_path: Path) -> None:
    config_path = _local_runner_config(tmp_path)
    config = load_operations_runner_config(config_path)
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        schedule, plan = _due_plan(repository)
        request = replace(
            _request(config_path, schedule, plan),
            requested_at=AS_OF + timedelta(seconds=10),
        )
        with pytest.raises(ValueError, match="not yet eligible"):
            OperationsJobRunner(
                config,
                OperationsRunnerRegistry(repository),
                transport=_SuccessTransport(),
                clock=lambda: AS_OF,
            ).run_once(request)
