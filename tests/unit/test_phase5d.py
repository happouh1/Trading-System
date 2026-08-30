from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trading_system.operations import (
    ApprovalAction,
    ApprovalEvent,
    CancellationAction,
    CancellationEvent,
    ControlStatus,
    HealthObservation,
    HealthStatus,
    IncidentAction,
    IncidentEvent,
    KillSwitchEvent,
    OperationalMode,
    OperationsControlConfigError,
    OperationsControlRegistry,
    OperationsJobRunner,
    OperationsMonitorEngine,
    OperationsRegistry,
    OperationsRunnerRegistry,
    ScheduleDefinition,
    SwitchAction,
    WorkerAction,
    WorkerInvocation,
    load_operations_control_config,
    load_operations_monitor_config,
    load_operations_runner_config,
)
from trading_system.operations.runner import JobRunRequest
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
MONITOR_CONFIG = ROOT / "config" / "operations.phase5b.v1.yaml"
RUNNER_CONFIG = ROOT / "config" / "operations.phase5c.v1.yaml"
CONTROL_CONFIG = ROOT / "config" / "operations.phase5d.v1.yaml"
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


class _SuccessTransport:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request: JobRunRequest, target: Path | None) -> WorkerInvocation:
        self.calls += 1
        return WorkerInvocation(0, {"status": "OK"}, b'{"status":"OK"}', b"")


def _seed(repository: SQLiteRepository) -> tuple[JobRunRequest, str]:
    monitor = load_operations_monitor_config(MONITOR_CONFIG)
    runner = load_operations_runner_config(RUNNER_CONFIG)
    schedule = ScheduleDefinition.create(
        name="phase5d-fixture",
        component="CORE_RESEARCH",
        mode=OperationalMode.OFFLINE,
        first_due_at=AS_OF,
        cadence_seconds=3600,
        config_hash=monitor.config_hash,
    )
    health = tuple(
        HealthObservation.create(
            component=component,
            observed_at=AS_OF,
            status=HealthStatus.HEALTHY,
            reasons=(),
            evidence_fingerprint=f"sha256:{component.lower()}",
            config_hash=monitor.config_hash,
        )
        for component in COMPONENTS
    )
    report, plan, alerts = OperationsMonitorEngine(monitor).evaluate(
        as_of=AS_OF,
        schedules=(schedule,),
        cursors=(),
        health=health,
        source_revision="sha256:phase5d-plan",
    )
    operations = OperationsRegistry(repository)
    operations.insert_schedule(schedule)
    operations.insert_schedule_plan(plan)
    for alert in alerts:
        operations.insert_alert(alert)
    operations.insert_monitor_report(report)
    request = JobRunRequest.create(
        schedule_plan_id=plan.plan_id,
        schedule_job_id=schedule.job_id,
        due_at=plan.due_jobs[0].due_at,
        requested_at=AS_OF,
        action=WorkerAction.EVIDENCE_NOOP,
        target=None,
        source_revision="sha256:phase5d-request",
        config_hash=runner.config_hash,
    )
    run_registry = OperationsRunnerRegistry(repository)
    run_registry.validate_due_request(request)
    run_registry.insert_run_request(request)
    return request, report.report_id


def _release(registry: OperationsControlRegistry) -> KillSwitchEvent:
    config = registry.config
    event = KillSwitchEvent.create(
        component=None,
        action=SwitchAction.RELEASE,
        known_at=AS_OF,
        operator_id="operator-a",
        reasons=("REVIEWED_OFFLINE_DIAGNOSTIC",),
        config=config,
    )
    registry.insert_kill_switch(event)
    return event


def _approve(registry: OperationsControlRegistry, request_id: str) -> ApprovalEvent:
    config = registry.config
    event = ApprovalEvent.create(
        request_id=request_id,
        operator_id="operator-a",
        action=ApprovalAction.GRANT,
        known_at=AS_OF,
        expires_at=AS_OF + timedelta(hours=1),
        reasons=("APPROVED_READ_ONLY_ACTION",),
        config=config,
    )
    registry.insert_approval(event)
    return event


def test_phase5d_config_is_fail_closed_and_local_only(tmp_path: Path) -> None:
    config = load_operations_control_config(CONTROL_CONFIG)
    assert config.default_global_engaged
    raw = json.loads(CONTROL_CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["remote_control_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OperationsControlConfigError, match="local and offline"):
        load_operations_control_config(invalid)


def test_default_control_state_halts_without_release_or_approval(tmp_path: Path) -> None:
    config = load_operations_control_config(CONTROL_CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        request, _ = _seed(repository)
        snapshot = OperationsControlRegistry(repository, config).snapshot(
            as_of=AS_OF, request_id=request.request_id
        )
    assert snapshot.status is ControlStatus.HALTED
    assert snapshot.global_kill_engaged
    assert "GLOBAL_KILL_ENGAGED" in snapshot.reasons
    assert any(reason.startswith("APPROVALS_ACTIVE") for reason in snapshot.reasons)


def test_release_and_unexpired_approval_authorize_controlled_run(tmp_path: Path) -> None:
    control_config = load_operations_control_config(CONTROL_CONFIG)
    runner_config = load_operations_runner_config(RUNNER_CONFIG)
    transport = _SuccessTransport()
    times = iter((AS_OF + timedelta(seconds=1), AS_OF + timedelta(seconds=2)))
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        request, _ = _seed(repository)
        control = OperationsControlRegistry(repository, control_config)
        _release(control)
        _approve(control, request.request_id)
        attempt = OperationsJobRunner(
            runner_config,
            OperationsRunnerRegistry(repository),
            transport=transport,
            clock=lambda: next(times),
            control_gate=control,
        ).run_once(request)
        snapshot = control.snapshot(
            as_of=AS_OF + timedelta(seconds=1), request_id=request.request_id
        )
    assert attempt.status.value == "SUCCEEDED"
    assert transport.calls == 1
    assert snapshot.status is ControlStatus.READY


def test_expired_or_revoked_approval_halts(tmp_path: Path) -> None:
    config = load_operations_control_config(CONTROL_CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        request, _ = _seed(repository)
        control = OperationsControlRegistry(repository, config)
        _release(control)
        grant = _approve(control, request.request_id)
        expired = control.snapshot(
            as_of=grant.expires_at or AS_OF, request_id=request.request_id
        )
        revoke = ApprovalEvent.create(
            request_id=request.request_id,
            operator_id="operator-a",
            action=ApprovalAction.REVOKE,
            known_at=AS_OF + timedelta(minutes=1),
            expires_at=None,
            reasons=("OPERATOR_REVOKED",),
            config=config,
        )
        control.insert_approval(revoke)
        revoked = control.snapshot(
            as_of=AS_OF + timedelta(minutes=2), request_id=request.request_id
        )
    assert expired.status is ControlStatus.HALTED
    assert revoked.status is ControlStatus.HALTED


def test_component_kill_and_cancellation_both_halt(tmp_path: Path) -> None:
    config = load_operations_control_config(CONTROL_CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        request, _ = _seed(repository)
        control = OperationsControlRegistry(repository, config)
        _release(control)
        _approve(control, request.request_id)
        component_kill = KillSwitchEvent.create(
            component="CORE_RESEARCH",
            action=SwitchAction.ENGAGE,
            known_at=AS_OF,
            operator_id="operator-a",
            reasons=("COMPONENT_MAINTENANCE",),
            config=config,
        )
        control.insert_kill_switch(component_kill)
        killed = control.snapshot(as_of=AS_OF, request_id=request.request_id)
        cancel = CancellationEvent.create(
            request_id=request.request_id,
            action=CancellationAction.REQUEST,
            known_at=AS_OF + timedelta(seconds=1),
            operator_id="operator-a",
            reasons=("OPERATOR_CANCELLED",),
            config=config,
        )
        control.insert_cancellation(cancel)
        cancelled = control.snapshot(
            as_of=AS_OF + timedelta(seconds=1), request_id=request.request_id
        )
    assert any(reason.startswith("COMPONENT_KILL") for reason in killed.reasons)
    assert "CANCELLATION_REQUESTED" in cancelled.reasons


def test_incident_transition_is_strict(tmp_path: Path) -> None:
    monitor = load_operations_monitor_config(MONITOR_CONFIG)
    control_config = load_operations_control_config(CONTROL_CONFIG)
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        schedule = ScheduleDefinition.create(
            name="overdue",
            component="PAPER",
            mode=OperationalMode.SHADOW,
            first_due_at=AS_OF - timedelta(minutes=10),
            cadence_seconds=3600,
            config_hash=monitor.config_hash,
        )
        health = tuple(
            HealthObservation.create(
                component=component,
                observed_at=AS_OF,
                status=HealthStatus.HEALTHY,
                reasons=(),
                evidence_fingerprint=f"sha256:{component.lower()}",
                config_hash=monitor.config_hash,
            )
            for component in COMPONENTS
        )
        _, plan, alerts = OperationsMonitorEngine(monitor).evaluate(
            as_of=AS_OF,
            schedules=(schedule,),
            cursors=(),
            health=health,
            source_revision="sha256:incident",
        )
        operations = OperationsRegistry(repository)
        operations.insert_schedule(schedule)
        operations.insert_schedule_plan(plan)
        operations.insert_alert(alerts[0])
        control = OperationsControlRegistry(repository, control_config)
        with pytest.raises(ValueError, match="ACKNOWLEDGE"):
            control.insert_incident(
                IncidentEvent.create(
                    alert_id=alerts[0].alert_id,
                    action=IncidentAction.RESOLVE,
                    known_at=AS_OF,
                    operator_id="operator-a",
                    reasons=("INVALID_DIRECT_RESOLUTION",),
                    config=control_config,
                )
            )
        acknowledge = IncidentEvent.create(
            alert_id=alerts[0].alert_id,
            action=IncidentAction.ACKNOWLEDGE,
            known_at=AS_OF,
            operator_id="operator-a",
            reasons=("INVESTIGATION_STARTED",),
            config=control_config,
        )
        control.insert_incident(acknowledge)
        resolve = IncidentEvent.create(
            alert_id=alerts[0].alert_id,
            action=IncidentAction.RESOLVE,
            known_at=AS_OF + timedelta(seconds=1),
            operator_id="operator-a",
            reasons=("CAUSE_RESOLVED",),
            config=control_config,
        )
        control.insert_incident(resolve)
        snapshot = control.snapshot(as_of=AS_OF + timedelta(seconds=1), request_id=None)
    assert snapshot.resolved_alert_ids == (alerts[0].alert_id,)
