"""Offline Phase 5 operations inspection and monitor planning commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from trading_system import PACKAGE_VERSION
from trading_system.operations.config import load_operations_config
from trading_system.operations.contracts import OperationsManifest
from trading_system.operations.control_config import load_operations_control_config
from trading_system.operations.control_registry import OperationsControlRegistry
from trading_system.operations.controls import (
    ApprovalAction,
    ApprovalEvent,
    CancellationAction,
    CancellationEvent,
    IncidentAction,
    IncidentEvent,
    KillSwitchEvent,
    SwitchAction,
)
from trading_system.operations.inspection import inspect_component
from trading_system.operations.monitor_config import load_operations_monitor_config
from trading_system.operations.monitoring import (
    HealthObservation,
    HealthStatus,
    OperationalMode,
    OperationsMonitorEngine,
    ScheduleCursor,
    ScheduleDefinition,
)
from trading_system.operations.registry import OperationsRegistry
from trading_system.operations.runner import JobRunRequest, OperationsJobRunner, WorkerAction
from trading_system.operations.runner_config import (
    OperationsRunnerConfig,
    load_operations_runner_config,
)
from trading_system.operations.runner_registry import OperationsRunnerRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json


def configure_operations_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    operations = commands.add_parser("operations")
    actions = operations.add_subparsers(dest="operations_command", required=True)
    validate = actions.add_parser("validate-config")
    validate.add_argument("--config", required=True)
    inspect = actions.add_parser("inspect")
    inspect.add_argument("--config", required=True)
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--registry-database", required=True)
    status = actions.add_parser("status")
    status.add_argument("--registry-database", required=True)
    status.add_argument("--manifest-id", required=True)
    validate_monitor = actions.add_parser("validate-monitor-config")
    validate_monitor.add_argument("--config", required=True)
    monitor = actions.add_parser("monitor")
    monitor.add_argument("--config", required=True)
    monitor.add_argument("--input", required=True)
    monitor.add_argument("--database", required=True)
    monitor_status = actions.add_parser("monitor-status")
    monitor_status.add_argument("--database", required=True)
    monitor_status.add_argument("--report-id", required=True)
    validate_runner = actions.add_parser("validate-runner-config")
    validate_runner.add_argument("--config", required=True)
    run_job = actions.add_parser("run-job")
    run_job.add_argument("--config", required=True)
    run_job.add_argument("--input", required=True)
    run_job.add_argument("--database", required=True)
    run_status = actions.add_parser("run-status")
    run_status.add_argument("--database", required=True)
    run_status.add_argument("--request-id", required=True)
    validate_control = actions.add_parser("validate-control-config")
    validate_control.add_argument("--config", required=True)
    prepare_run = actions.add_parser("prepare-run")
    prepare_run.add_argument("--runner-config", required=True)
    prepare_run.add_argument("--input", required=True)
    prepare_run.add_argument("--database", required=True)
    approval = actions.add_parser("approval")
    approval.add_argument("--config", required=True)
    approval.add_argument("--input", required=True)
    approval.add_argument("--database", required=True)
    kill_switch = actions.add_parser("kill-switch")
    kill_switch.add_argument("--config", required=True)
    kill_switch.add_argument("--input", required=True)
    kill_switch.add_argument("--database", required=True)
    cancellation = actions.add_parser("cancellation")
    cancellation.add_argument("--config", required=True)
    cancellation.add_argument("--input", required=True)
    cancellation.add_argument("--database", required=True)
    incident = actions.add_parser("incident")
    incident.add_argument("--config", required=True)
    incident.add_argument("--input", required=True)
    incident.add_argument("--database", required=True)
    control_status = actions.add_parser("control-status")
    control_status.add_argument("--config", required=True)
    control_status.add_argument("--database", required=True)
    control_status.add_argument("--as-of", required=True)
    control_status.add_argument("--request-id")
    controlled_run = actions.add_parser("controlled-run")
    controlled_run.add_argument("--runner-config", required=True)
    controlled_run.add_argument("--control-config", required=True)
    controlled_run.add_argument("--input", required=True)
    controlled_run.add_argument("--database", required=True)


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("known_at must be an ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("known_at must be timezone-aware")
    return result


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{name} must be an array of nonempty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _handle_monitor(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-monitor-config":
        config = load_operations_monitor_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "monitor-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload, status, count = OperationsRegistry(repository).monitor_status(args.report_id)
        print(
            canonical_json(
                {
                    "report_id": args.report_id,
                    "status": status,
                    "alert_count": count,
                    "report": json.loads(payload),
                }
            )
        )
        return 0
    config = load_operations_monitor_config(args.config)
    root = _object(
        json.loads(Path(args.input).read_text(encoding="utf-8")),
        "monitor input",
    )
    if set(root) != {"as_of", "source_revision", "jobs", "health"}:
        raise ValueError("monitor input fields are invalid")
    as_of = _time(root["as_of"])
    source_revision = root["source_revision"]
    if not isinstance(source_revision, str) or not source_revision:
        raise ValueError("monitor source revision is required")
    raw_jobs = root["jobs"]
    if not isinstance(raw_jobs, list):
        raise ValueError("monitor jobs must be an array")
    schedules = []
    cursors = []
    for raw in raw_jobs:
        job = _object(raw, "monitor job")
        if set(job) != {
            "name",
            "component",
            "mode",
            "first_due_at",
            "cadence_seconds",
            "last_completed_at",
        }:
            raise ValueError("monitor job fields are invalid")
        cadence = job["cadence_seconds"]
        if not isinstance(cadence, int) or isinstance(cadence, bool):
            raise ValueError("monitor job cadence_seconds must be an integer")
        definition = ScheduleDefinition.create(
            name=_string(job["name"], "monitor job name"),
            component=_string(job["component"], "monitor job component"),
            mode=OperationalMode(_string(job["mode"], "monitor job mode")),
            first_due_at=_time(job["first_due_at"]),
            cadence_seconds=cadence,
            config_hash=config.config_hash,
        )
        schedules.append(definition)
        last_completed = job["last_completed_at"]
        cursors.append(
            ScheduleCursor(
                definition.job_id,
                None if last_completed is None else _time(last_completed),
            )
        )
    raw_health = root["health"]
    if not isinstance(raw_health, list):
        raise ValueError("monitor health must be an array")
    health = []
    for raw in raw_health:
        item = _object(raw, "health observation")
        if set(item) != {
            "component",
            "observed_at",
            "status",
            "reasons",
            "evidence_fingerprint",
        }:
            raise ValueError("health observation fields are invalid")
        health.append(
            HealthObservation.create(
                component=_string(item["component"], "health component"),
                observed_at=_time(item["observed_at"]),
                status=HealthStatus(_string(item["status"], "health status")),
                reasons=_string_tuple(item["reasons"], "health reasons"),
                evidence_fingerprint=_string(
                    item["evidence_fingerprint"], "health evidence fingerprint"
                ),
                config_hash=config.config_hash,
            )
        )
    report, plan, alerts = OperationsMonitorEngine(config).evaluate(
        as_of=as_of,
        schedules=tuple(schedules),
        cursors=tuple(cursors),
        health=tuple(health),
        source_revision=source_revision,
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        for schedule in schedules:
            registry.insert_schedule(schedule)
        registry.insert_schedule_plan(plan)
        for observation in health:
            registry.insert_health(observation)
        for alert in alerts:
            registry.insert_alert(alert)
        registry.insert_monitor_report(report)
    print(canonical_json({"report": report, "plan": plan, "alerts": alerts}))
    return 0


def _load_run_request(
    config_path: str, input_path: str
) -> tuple[OperationsRunnerConfig, JobRunRequest]:
    config = load_operations_runner_config(config_path)
    root = _object(json.loads(Path(input_path).read_text(encoding="utf-8")), "run input")
    if set(root) != {
        "schedule_plan_id",
        "schedule_job_id",
        "due_at",
        "requested_at",
        "action",
        "target",
        "source_revision",
    }:
        raise ValueError("run input fields are invalid")
    target = root["target"]
    if target is not None and (not isinstance(target, str) or not target):
        raise ValueError("run target must be null or a nonempty string")
    request = JobRunRequest.create(
        schedule_plan_id=_string(root["schedule_plan_id"], "schedule plan ID"),
        schedule_job_id=_string(root["schedule_job_id"], "schedule job ID"),
        due_at=_time(root["due_at"]),
        requested_at=_time(root["requested_at"]),
        action=WorkerAction(_string(root["action"], "worker action")),
        target=target,
        source_revision=_string(root["source_revision"], "run source revision"),
        config_hash=config.config_hash,
    )
    return config, request


def _handle_runner(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-runner-config":
        config = load_operations_runner_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "run-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            payload, attempts = OperationsRunnerRegistry(repository).status(args.request_id)
        print(
            canonical_json(
                {
                    "request": json.loads(payload),
                    "attempts": attempts,
                    "attempt_count": len(attempts),
                }
            )
        )
        return 0
    config, request = _load_run_request(args.config, args.input)
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsRunnerRegistry(repository)
        attempt = OperationsJobRunner(config, registry).run_once(request)
    print(
        canonical_json(
            {
                "request": request,
                "attempt": attempt,
                "packaged_worker_only": True,
                "shell_used": False,
                "network_used": False,
                "credential_accessed": False,
                "broker_write_performed": False,
            }
        )
    )
    return 0


def _control_input(path: str, expected: set[str]) -> dict[str, object]:
    root = _object(json.loads(Path(path).read_text(encoding="utf-8")), "control input")
    if set(root) != expected:
        raise ValueError("control input fields are invalid")
    return root


def _handle_control(args: argparse.Namespace) -> int:
    if args.operations_command == "validate-control-config":
        config = load_operations_control_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "prepare-run":
        _, request = _load_run_request(args.runner_config, args.input)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = OperationsRunnerRegistry(repository)
            registry.validate_due_request(request)
            registry.insert_run_request(request)
        print(canonical_json({"request": request, "prepared": True, "worker_invoked": False}))
        return 0
    control_path = args.config if hasattr(args, "config") else args.control_config
    config = load_operations_control_config(control_path)
    if args.operations_command == "control-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            control_registry = OperationsControlRegistry(repository, config)
            snapshot = control_registry.snapshot(
                as_of=_time(args.as_of),
                request_id=args.request_id,
            )
            control_registry.insert_snapshot(snapshot)
        print(canonical_json({"snapshot": snapshot, "remote_control_used": False}))
        return 0
    if args.operations_command == "controlled-run":
        runner_config, request = _load_run_request(args.runner_config, args.input)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            control = OperationsControlRegistry(repository, config)
            attempt = OperationsJobRunner(
                runner_config,
                OperationsRunnerRegistry(repository),
                control_gate=control,
            ).run_once(request)
        print(
            canonical_json(
                {
                    "request": request,
                    "attempt": attempt,
                    "control_enforced": True,
                    "remote_control_used": False,
                    "broker_write_performed": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "request_id",
            "operator_id",
            "action",
            "known_at",
            "expires_at",
            "reasons",
        }
        if args.operations_command == "approval"
        else {"component", "operator_id", "action", "known_at", "reasons"}
        if args.operations_command == "kill-switch"
        else {"request_id", "operator_id", "action", "known_at", "reasons"}
        if args.operations_command == "cancellation"
        else {"alert_id", "operator_id", "action", "known_at", "reasons"},
    )
    reasons = _string_tuple(root["reasons"], "control reasons")
    operator_id = _string(root["operator_id"], "operator ID")
    known_at = _time(root["known_at"])
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        control_registry = OperationsControlRegistry(repository, config)
        if args.operations_command == "approval":
            expires = root["expires_at"]
            approval_event = ApprovalEvent.create(
                request_id=_string(root["request_id"], "request ID"),
                operator_id=operator_id,
                action=ApprovalAction(_string(root["action"], "approval action")),
                known_at=known_at,
                expires_at=None if expires is None else _time(expires),
                reasons=reasons,
                config=config,
            )
            control_registry.insert_approval(approval_event)
            output_event: object = approval_event
        elif args.operations_command == "kill-switch":
            component = root["component"]
            if component is not None and (not isinstance(component, str) or not component):
                raise ValueError("kill switch component must be null or nonempty")
            switch_event = KillSwitchEvent.create(
                component=component,
                action=SwitchAction(_string(root["action"], "switch action")),
                known_at=known_at,
                operator_id=operator_id,
                reasons=reasons,
                config=config,
            )
            control_registry.insert_kill_switch(switch_event)
            output_event = switch_event
        elif args.operations_command == "cancellation":
            cancellation_event = CancellationEvent.create(
                request_id=_string(root["request_id"], "request ID"),
                action=CancellationAction(_string(root["action"], "cancellation action")),
                known_at=known_at,
                operator_id=operator_id,
                reasons=reasons,
                config=config,
            )
            control_registry.insert_cancellation(cancellation_event)
            output_event = cancellation_event
        else:
            incident_event = IncidentEvent.create(
                alert_id=_string(root["alert_id"], "alert ID"),
                action=IncidentAction(_string(root["action"], "incident action")),
                known_at=known_at,
                operator_id=operator_id,
                reasons=reasons,
                config=config,
            )
            control_registry.insert_incident(incident_event)
            output_event = incident_event
    print(
        canonical_json(
            {"event": output_event, "recorded": True, "operator_authenticated": False}
        )
    )
    return 0


def handle_operations(args: argparse.Namespace) -> int:
    if args.operations_command in {
        "validate-control-config",
        "prepare-run",
        "approval",
        "kill-switch",
        "cancellation",
        "incident",
        "control-status",
        "controlled-run",
    }:
        return _handle_control(args)
    if args.operations_command in {
        "validate-runner-config",
        "run-job",
        "run-status",
    }:
        return _handle_runner(args)
    if args.operations_command in {
        "validate-monitor-config",
        "monitor",
        "monitor-status",
    }:
        return _handle_monitor(args)
    if args.operations_command == "validate-config":
        config = load_operations_config(args.config)
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    if args.operations_command == "status":
        with SQLiteRepository(args.registry_database) as repository:
            repository.migrate()
            payload, status, count = OperationsRegistry(repository).status(args.manifest_id)
        print(
            canonical_json(
                {
                    "manifest_id": args.manifest_id,
                    "status": status,
                    "component_count": count,
                    "manifest": json.loads(payload),
                }
            )
        )
        return 0
    config = load_operations_config(args.config)
    input_path = Path(args.input).resolve()
    root = _object(json.loads(input_path.read_text(encoding="utf-8")), "operations input")
    if set(root) != {"known_at", "source_revision", "databases"}:
        raise ValueError("operations input fields are invalid")
    known_at = _time(root["known_at"])
    source_revision = str(root["source_revision"])
    if not source_revision:
        raise ValueError("operations source revision is required")
    databases = _object(root["databases"], "operations databases")
    if set(databases) != set(config.components):
        raise ValueError("operations input must bind every configured component")
    evidence = []
    source_paths: set[Path] = set()
    for component in config.components:
        binding = _object(databases[component], f"{component} database")
        if set(binding) != {"label", "path"}:
            raise ValueError(f"{component} database fields are invalid")
        label = binding["label"]
        raw_path_value = binding["path"]
        if not isinstance(label, str) or not label:
            raise ValueError(f"{component} database label is required")
        if not isinstance(raw_path_value, str) or not raw_path_value:
            raise ValueError(f"{component} database path is required")
        raw_path = Path(raw_path_value)
        resolved_path = raw_path if raw_path.is_absolute() else input_path.parent / raw_path
        resolved_path = resolved_path.resolve()
        source_paths.add(resolved_path)
        evidence.append(
            inspect_component(
                config,
                component=component,
                database_label=label,
                database_path=resolved_path,
                known_at=known_at,
            )
        )
    evidence_tuple = tuple(evidence)
    manifest = OperationsManifest.create(
        known_at=known_at,
        evidence=evidence_tuple,
        config_hash=config.config_hash,
        code_version=PACKAGE_VERSION,
        source_revision=source_revision,
    )
    registry_path = Path(args.registry_database).resolve()
    if registry_path in source_paths:
        raise ValueError("operations registry database must be separate from source databases")
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsRegistry(repository)
        registry.insert_manifest(manifest)
        for item in evidence_tuple:
            registry.insert_evidence(manifest.manifest_id, item)
    print(canonical_json({"manifest": manifest, "components": evidence_tuple}))
    return 0
