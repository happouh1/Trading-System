"""Offline Phase 5 operations inspection and monitor planning commands."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from trading_system import PACKAGE_VERSION
from trading_system.operations.campaign_config import load_operations_campaign_config
from trading_system.operations.campaign_contracts import CampaignWindowRequest
from trading_system.operations.campaign_registry import OperationsCampaignRegistry
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
from trading_system.operations.observation_config import load_observation_plan_config
from trading_system.operations.observation_contracts import ObservationPlanWindow
from trading_system.operations.observation_registry import ObservationPlanRegistry
from trading_system.operations.registry import OperationsRegistry
from trading_system.operations.release_config import load_operations_release_config
from trading_system.operations.release_registry import OperationsReleaseRegistry
from trading_system.operations.resilience import OperationsResilienceService
from trading_system.operations.resilience_config import load_operations_resilience_config
from trading_system.operations.resilience_registry import OperationsResilienceRegistry
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
    validate_resilience = actions.add_parser("validate-resilience-config")
    validate_resilience.add_argument("--config", required=True)
    backup_database = actions.add_parser("backup-database")
    backup_database.add_argument("--config", required=True)
    backup_database.add_argument("--input", required=True)
    backup_database.add_argument("--database", required=True)
    verify_restore = actions.add_parser("verify-restore")
    verify_restore.add_argument("--config", required=True)
    verify_restore.add_argument("--input", required=True)
    verify_restore.add_argument("--database", required=True)
    retention_status = actions.add_parser("retention-status")
    retention_status.add_argument("--config", required=True)
    retention_status.add_argument("--database", required=True)
    retention_status.add_argument("--as-of", required=True)
    validate_release = actions.add_parser("validate-release-config")
    validate_release.add_argument("--config", required=True)
    release_evidence = actions.add_parser("release-evidence")
    release_evidence.add_argument("--config", required=True)
    release_evidence.add_argument("--input", required=True)
    release_evidence.add_argument("--database", required=True)
    release_status = actions.add_parser("release-status")
    release_status.add_argument("--database", required=True)
    release_status.add_argument("--bundle-id", required=True)
    validate_campaign = actions.add_parser("validate-campaign-config")
    validate_campaign.add_argument("--config", required=True)
    shadow_campaign = actions.add_parser("shadow-campaign")
    shadow_campaign.add_argument("--config", required=True)
    shadow_campaign.add_argument("--input", required=True)
    shadow_campaign.add_argument("--database", required=True)
    campaign_status = actions.add_parser("campaign-status")
    campaign_status.add_argument("--database", required=True)
    campaign_status.add_argument("--report-id", required=True)
    validate_observation = actions.add_parser("validate-observation-plan-config")
    validate_observation.add_argument("--config", required=True)
    register_observation = actions.add_parser("register-observation-plan")
    register_observation.add_argument("--config", required=True)
    register_observation.add_argument("--input", required=True)
    register_observation.add_argument("--database", required=True)
    observation_status = actions.add_parser("observation-plan-status")
    observation_status.add_argument("--database", required=True)
    observation_status.add_argument("--plan-id", required=True)
    reconcile_observation = actions.add_parser("reconcile-observation-plan")
    reconcile_observation.add_argument("--config", required=True)
    reconcile_observation.add_argument("--input", required=True)
    reconcile_observation.add_argument("--database", required=True)
    reconciliation_status = actions.add_parser("observation-reconciliation-status")
    reconciliation_status.add_argument("--database", required=True)
    reconciliation_status.add_argument("--reconciliation-id", required=True)


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


def _handle_resilience(args: argparse.Namespace) -> int:
    config = load_operations_resilience_config(args.config)
    if args.operations_command == "validate-resilience-config":
        print(canonical_json({"config_hash": config.config_hash, "valid": True}))
        return 0
    registry_path = Path(args.database).resolve()
    with SQLiteRepository(registry_path) as repository:
        repository.migrate()
        registry = OperationsResilienceRegistry(repository, config)
        if args.operations_command == "retention-status":
            report = registry.retention_report(_time(args.as_of))
            registry.insert_retention_report(report)
            print(
                canonical_json(
                    {
                        "report": report,
                        "deletion_performed": False,
                        "network_used": False,
                        "broker_write_performed": False,
                    }
                )
            )
            return 0
        root = _object(
            json.loads(Path(args.input).read_text(encoding="utf-8")),
            "resilience input",
        )
        service = OperationsResilienceService(config, registry)
        if args.operations_command == "backup-database":
            if set(root) != {"source_path", "known_at", "source_revision"}:
                raise ValueError("backup input fields are invalid")
            source_path = _string(root["source_path"], "backup source path")
            source = (config.workspace_root / source_path).resolve()
            if source == registry_path:
                raise ValueError("resilience registry must be separate from backup source")
            manifest = service.create_backup(
                source_path=source_path,
                known_at=_time(root["known_at"]),
                source_revision=_string(root["source_revision"], "backup source revision"),
            )
            print(
                canonical_json(
                    {
                        "manifest": manifest,
                        "source_opened_read_only": True,
                        "network_used": False,
                        "broker_write_performed": False,
                    }
                )
            )
            return 0
        if set(root) != {"backup_id", "known_at"}:
            raise ValueError("restore input fields are invalid")
        verification = service.verify_restore(
            backup_id=_string(root["backup_id"], "backup ID"),
            known_at=_time(root["known_at"]),
        )
        print(
            canonical_json(
                {
                    "verification": verification,
                    "isolated_restore_only": True,
                    "promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                }
            )
        )
        return 0


def _handle_release(args: argparse.Namespace) -> int:
    if args.operations_command == "release-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json
                   FROM operations_release_evidence_bundles WHERE bundle_id = ?""",
                (args.bundle_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown release evidence bundle")
        print(
            canonical_json(
                {
                    "bundle_id": args.bundle_id,
                    "status": str(row[0]),
                    "bundle": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_operations_release_config(args.config)
    if args.operations_command == "validate-release-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "as_of",
            "readiness_manifest_id",
            "monitor_report_id",
            "control_snapshot_id",
            "run_request_id",
            "backup_id",
            "restore_verification_id",
            "source_revision",
        },
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsReleaseRegistry(repository, config)
        bundle = registry.evaluate(
            as_of=_time(root["as_of"]),
            readiness_manifest_id=_string(
                root["readiness_manifest_id"], "readiness manifest ID"
            ),
            monitor_report_id=_string(root["monitor_report_id"], "monitor report ID"),
            control_snapshot_id=_string(
                root["control_snapshot_id"], "control snapshot ID"
            ),
            run_request_id=_string(root["run_request_id"], "run request ID"),
            backup_id=_string(root["backup_id"], "backup ID"),
            restore_verification_id=_string(
                root["restore_verification_id"], "restore verification ID"
            ),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(bundle)
    print(
        canonical_json(
            {
                "bundle": bundle,
                "inserted": inserted,
                "production_readiness_claim": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_campaign(args: argparse.Namespace) -> int:
    if args.operations_command == "campaign-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json FROM operations_shadow_campaign_reports
                   WHERE report_id = ?""",
                (args.report_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown shadow campaign report")
            count_row = repository.connection.execute(
                """SELECT COUNT(*) FROM operations_shadow_campaign_windows
                   WHERE report_id = ?""",
                (args.report_id,),
            ).fetchone()
        print(
            canonical_json(
                {
                    "report_id": args.report_id,
                    "status": str(row[0]),
                    "window_count": 0 if count_row is None else int(count_row[0]),
                    "report": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_operations_campaign_config(args.config)
    if args.operations_command == "validate-campaign-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {
            "campaign_name",
            "start_at",
            "end_at",
            "evaluated_at",
            "windows",
            "source_revision",
        },
    )
    raw_windows = root["windows"]
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ValueError("shadow campaign windows must be a nonempty array")
    requests: list[CampaignWindowRequest] = []
    for raw_window in raw_windows:
        window = _object(raw_window, "shadow campaign window")
        if set(window) != {"window_id", "expected_as_of", "bundle_id"}:
            raise ValueError("shadow campaign window fields are invalid")
        raw_bundle_id = window["bundle_id"]
        if raw_bundle_id is not None and not isinstance(raw_bundle_id, str):
            raise ValueError("shadow campaign bundle ID must be a string or null")
        requests.append(
            CampaignWindowRequest(
                _string(window["window_id"], "shadow campaign window ID"),
                _time(window["expected_as_of"]),
                raw_bundle_id,
            )
        )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = OperationsCampaignRegistry(repository, config)
        report = registry.evaluate(
            campaign_name=_string(root["campaign_name"], "campaign name"),
            start_at=_time(root["start_at"]),
            end_at=_time(root["end_at"]),
            evaluated_at=_time(root["evaluated_at"]),
            requests=tuple(requests),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert(report)
    print(
        canonical_json(
            {
                "report": report,
                "inserted": inserted,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def _handle_observation_plan(args: argparse.Namespace) -> int:
    if args.operations_command == "observation-plan-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                "SELECT status, payload_json FROM operations_observation_plans WHERE plan_id = ?",
                (args.plan_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown observation plan")
            count = repository.connection.execute(
                "SELECT COUNT(*) FROM operations_observation_plan_windows WHERE plan_id = ?",
                (args.plan_id,),
            ).fetchone()
        print(
            canonical_json(
                {
                    "plan_id": args.plan_id,
                    "status": str(row[0]),
                    "window_count": 0 if count is None else int(count[0]),
                    "plan": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "observation-reconciliation-status":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            row = repository.connection.execute(
                """SELECT status, payload_json
                   FROM operations_observation_plan_reconciliations
                   WHERE reconciliation_id = ?""",
                (args.reconciliation_id,),
            ).fetchone()
        if row is None:
            raise ValueError("unknown observation plan reconciliation")
        print(
            canonical_json(
                {
                    "reconciliation_id": args.reconciliation_id,
                    "status": str(row[0]),
                    "reconciliation": json.loads(str(row[1])),
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    config = load_observation_plan_config(args.config)
    if args.operations_command == "validate-observation-plan-config":
        print(
            canonical_json(
                {
                    "config_hash": config.config_hash,
                    "valid": True,
                    "production_readiness_claim": False,
                    "automatic_promotion_enabled": False,
                }
            )
        )
        return 0
    if args.operations_command == "register-observation-plan":
        root = _control_input(
            args.input,
            {
                "campaign_name",
                "registered_at",
                "start_at",
                "end_at",
                "windows",
                "source_revision",
            },
        )
        raw_windows = root["windows"]
        if not isinstance(raw_windows, list) or not raw_windows:
            raise ValueError("observation plan windows must be a nonempty array")
        windows: list[ObservationPlanWindow] = []
        for raw_window in raw_windows:
            window = _object(raw_window, "observation plan window")
            if set(window) != {"window_id", "expected_as_of"}:
                raise ValueError("observation plan window fields are invalid")
            windows.append(
                ObservationPlanWindow(
                    _string(window["window_id"], "observation plan window ID"),
                    _time(window["expected_as_of"]),
                )
            )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = ObservationPlanRegistry(repository, config)
            plan = registry.create_plan(
                campaign_name=_string(root["campaign_name"], "campaign name"),
                registered_at=_time(root["registered_at"]),
                start_at=_time(root["start_at"]),
                end_at=_time(root["end_at"]),
                windows=tuple(windows),
                source_revision=_string(root["source_revision"], "source revision"),
            )
            inserted = registry.insert_plan(plan)
        print(
            canonical_json(
                {
                    "plan": plan,
                    "inserted": inserted,
                    "production_readiness_claim": False,
                    "automatic_promotion_performed": False,
                    "network_used": False,
                    "broker_write_performed": False,
                    "live_trading_enabled": False,
                }
            )
        )
        return 0
    root = _control_input(
        args.input,
        {"plan_id", "campaign_report_id", "reconciled_at", "source_revision"},
    )
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = ObservationPlanRegistry(repository, config)
        reconciliation = registry.reconcile(
            plan_id=_string(root["plan_id"], "observation plan ID"),
            campaign_report_id=_string(root["campaign_report_id"], "campaign report ID"),
            reconciled_at=_time(root["reconciled_at"]),
            source_revision=_string(root["source_revision"], "source revision"),
        )
        inserted = registry.insert_reconciliation(reconciliation)
    print(
        canonical_json(
            {
                "reconciliation": reconciliation,
                "inserted": inserted,
                "production_readiness_claim": False,
                "automatic_promotion_performed": False,
                "network_used": False,
                "broker_write_performed": False,
                "live_trading_enabled": False,
            }
        )
    )
    return 0


def handle_operations(args: argparse.Namespace) -> int:
    if args.operations_command in {
        "validate-observation-plan-config",
        "register-observation-plan",
        "observation-plan-status",
        "reconcile-observation-plan",
        "observation-reconciliation-status",
    }:
        return _handle_observation_plan(args)
    if args.operations_command in {
        "validate-campaign-config",
        "shadow-campaign",
        "campaign-status",
    }:
        return _handle_campaign(args)
    if args.operations_command in {
        "validate-release-config",
        "release-evidence",
        "release-status",
    }:
        return _handle_release(args)
    if args.operations_command in {
        "validate-resilience-config",
        "backup-database",
        "verify-restore",
        "retention-status",
    }:
        return _handle_resilience(args)
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
