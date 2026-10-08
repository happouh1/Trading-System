"""Phase 3B lifecycle CLI; no external broker connectivity."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_system import PACKAGE_VERSION
from trading_system.market_data import XNYSCalendar
from trading_system.paper.adapters import InternalSimulatorAdapter
from trading_system.paper.bridge import stage_shadow_decision
from trading_system.paper.config import load_paper_config
from trading_system.paper.contracts import PaperMode, PaperSession, RuntimeState
from trading_system.paper.registry import PaperRegistry
from trading_system.paper.runtime import PaperRuntime
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json


def configure_paper_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    paper = commands.add_parser("paper")
    actions = paper.add_subparsers(dest="paper_command", required=True)
    start = actions.add_parser("start")
    start.add_argument("--database", required=True)
    start.add_argument("--session-id", required=True)
    start.add_argument("--config", required=True)
    start.add_argument("--data-revision", required=True)
    start.add_argument("--calendar-version", required=True)
    start.add_argument("--enable-simulated-paper", action="store_true")
    burn_in = actions.add_parser("start-burn-in")
    burn_in.add_argument("--database", required=True)
    burn_in.add_argument("--session-id", required=True)
    burn_in.add_argument("--config", required=True)
    burn_in.add_argument("--started-at", required=True)
    burn_in.add_argument("--project-root", default=".")
    prospective = actions.add_parser("start-prospective-shadow")
    prospective.add_argument("--database", required=True)
    prospective.add_argument("--session-id", required=True)
    prospective.add_argument("--config", required=True)
    prospective.add_argument("--runtime-lock", required=True)
    prospective.add_argument("--started-at", required=True)
    prospective.add_argument("--project-root", default=".")
    scheduled_target = actions.add_parser("scheduled-shadow-target")
    scheduled_target.add_argument("--schedule", required=True)
    scheduled_target.add_argument("--action", choices=("START", "POST_CLOSE"), required=True)
    scheduled_target.add_argument("--as-of", required=True)
    scheduled_target.add_argument("--project-root", default=".")
    scheduled_preflight = actions.add_parser("scheduled-shadow-preflight")
    scheduled_preflight.add_argument("--schedule", required=True)
    scheduled_preflight.add_argument("--as-of", required=True)
    scheduled_preflight.add_argument("--project-root", default=".")
    scheduled_start = actions.add_parser("scheduled-shadow-start")
    scheduled_start.add_argument("--schedule", required=True)
    scheduled_start.add_argument("--as-of", required=True)
    scheduled_start.add_argument("--project-root", default=".")
    scheduled_start.add_argument("--database-override")
    scheduled_complete = actions.add_parser("scheduled-shadow-complete")
    scheduled_complete.add_argument("--schedule", required=True)
    scheduled_complete.add_argument("--as-of", required=True)
    scheduled_complete.add_argument("--project-root", default=".")
    scheduled_complete.add_argument("--database-override")
    for name in (
        "scheduled-shadow-audit-target",
        "scheduled-shadow-audit",
        "scheduled-shadow-audit-status",
    ):
        audit_parser = actions.add_parser(name)
        audit_parser.add_argument("--audit-config", required=True)
        audit_parser.add_argument("--as-of", required=True)
        audit_parser.add_argument("--project-root", default=".")
        if name != "scheduled-shadow-audit-target":
            audit_parser.add_argument("--database-override")
    resume = actions.add_parser("resume")
    resume.add_argument("--database", required=True)
    resume.add_argument("--session-id", required=True)
    resume.add_argument("--config", required=True)
    resume.add_argument("--data-revision", required=True)
    resume.add_argument("--calendar-version", required=True)
    stage = actions.add_parser("stage-decision")
    stage.add_argument("--database", required=True)
    stage.add_argument("--session-id", required=True)
    stage.add_argument("--decision-id", required=True)
    stage.add_argument("--as-of", required=True)
    enable = actions.add_parser("enable")
    enable.add_argument("--database", required=True)
    enable.add_argument("--session-id", required=True)
    enable.add_argument("--config", required=True)
    enable.add_argument("--data-revision", required=True)
    enable.add_argument("--calendar-version", required=True)
    enable.add_argument("--enable-paper", action="store_true")
    for name in ("status", "halt", "drain", "reconcile", "report"):
        parser = actions.add_parser(name)
        parser.add_argument("--database", required=True)
        parser.add_argument("--session-id", required=True)
        if name == "report":
            parser.add_argument("--output", required=True)


def handle_paper(args: argparse.Namespace) -> int:
    command = str(args.paper_command)
    if command in {
        "scheduled-shadow-audit-target",
        "scheduled-shadow-audit",
        "scheduled-shadow-audit-status",
    }:
        from trading_system.paper.prospective_shadow_audit import (
            audit_scheduled_shadow_day,
            inspect_shadow_audit_target,
            load_prospective_shadow_audit_config,
            shadow_audit_status,
        )
        from trading_system.paper.prospective_shadow_orchestrator import (
            load_prospective_shadow_schedule,
        )

        root = Path(args.project_root).resolve()
        audit_config = load_prospective_shadow_audit_config(args.audit_config)
        schedule = load_prospective_shadow_schedule(root / audit_config.schedule)
        as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00"))
        if command == "scheduled-shadow-audit-target":
            audit_result = inspect_shadow_audit_target(
                schedule, audit_config, as_of=as_of
            )
        elif command == "scheduled-shadow-audit":
            audit_result = audit_scheduled_shadow_day(
                schedule,
                audit_config,
                project_root=root,
                as_of=as_of,
                database_override=args.database_override,
            )
        else:
            audit_result = shadow_audit_status(
                schedule,
                audit_config,
                project_root=root,
                as_of=as_of,
                database_override=args.database_override,
            )
        print(canonical_json(audit_result))
        return 0
    if command in {
        "scheduled-shadow-preflight",
        "scheduled-shadow-target",
        "scheduled-shadow-start",
        "scheduled-shadow-complete",
    }:
        from trading_system.paper.prospective_shadow_orchestrator import (
            complete_scheduled_shadow_day,
            inspect_scheduled_shadow_preflight,
            inspect_scheduled_shadow_target,
            load_prospective_shadow_schedule,
            start_scheduled_shadow_day,
        )

        schedule = load_prospective_shadow_schedule(args.schedule)
        as_of = datetime.fromisoformat(str(args.as_of).replace("Z", "+00:00"))
        if command == "scheduled-shadow-preflight":
            scheduled_result = inspect_scheduled_shadow_preflight(
                schedule,
                schedule_path=args.schedule,
                project_root=args.project_root,
                as_of=as_of,
            )
        elif command == "scheduled-shadow-target":
            scheduled_result = inspect_scheduled_shadow_target(
                schedule, as_of=as_of, action=str(args.action)
            )
        elif command == "scheduled-shadow-start":
            scheduled_result = start_scheduled_shadow_day(
                schedule,
                schedule_path=args.schedule,
                project_root=args.project_root,
                as_of=as_of,
                database_override=args.database_override,
            )
        else:
            scheduled_result = complete_scheduled_shadow_day(
                schedule,
                project_root=args.project_root,
                as_of=as_of,
                database_override=args.database_override,
            )
        print(canonical_json(scheduled_result))
        return 0
    if command == "start-prospective-shadow":
        from trading_system.paper.prospective_shadow_launch import (
            start_prospective_shadow_session,
        )

        started_at = datetime.fromisoformat(str(args.started_at).replace("Z", "+00:00"))
        prospective_result = start_prospective_shadow_session(
            database=args.database,
            config_path=args.config,
            runtime_lock_path=args.runtime_lock,
            project_root=args.project_root,
            session_id=args.session_id,
            started_at=started_at,
        )
        print(canonical_json(prospective_result))
        return 0
    if command == "start-burn-in":
        from trading_system.paper.burn_in_start import start_locked_burn_in_session

        started_at = datetime.fromisoformat(str(args.started_at).replace("Z", "+00:00"))
        locked_result = start_locked_burn_in_session(
            database=args.database,
            config_path=args.config,
            project_root=args.project_root,
            session_id=args.session_id,
            started_at=started_at,
        )
        print(canonical_json(locked_result))
        return 0
    now = datetime.now(UTC)
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = PaperRegistry(repository)
        if command == "start":
            config = load_paper_config(args.config)
            mode = (PaperMode.SIMULATED if args.enable_simulated_paper else PaperMode.SHADOW)
            session = PaperSession(
                args.session_id, now, mode, PACKAGE_VERSION, config.config_hash,
                args.data_revision, args.calendar_version,
            )
            registry.insert_session(session)
            runtime = PaperRuntime(registry, args.session_id, mode, InternalSimulatorAdapter())
            state = runtime.start(now)
            result: dict[str, object] = {"session_id": args.session_id, "state": state}
        elif command == "resume":
            config = load_paper_config(args.config)
            payload = registry.session_payload(args.session_id)
            expected = {
                "code_version": PACKAGE_VERSION,
                "config_hash": config.config_hash,
                "data_revision": args.data_revision,
                "calendar_version": args.calendar_version,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise ValueError("paper resume identity does not match stored session")
            state = registry.current_state(args.session_id)
            if state in (RuntimeState.STOPPED, RuntimeState.CREATED):
                raise ValueError(f"paper session cannot resume from {state.value}")
            result = {"session_id": args.session_id, "state": state,
                      "checkpoint": registry.latest_checkpoint(args.session_id)}
        elif command == "stage-decision":
            occurred_at = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
            if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
                raise ValueError("--as-of must be a timezone-aware timestamp")
            intent = stage_shadow_decision(
                repository, args.session_id, args.decision_id,
                occurred_at.astimezone(UTC), XNYSCalendar(),
            )
            result = {
                "session_id": args.session_id,
                "decision_id": args.decision_id,
                "intent_id": intent.intent_id,
                "scheduled_open": intent.scheduled_open,
                "status": intent.status,
                "network_used": False,
                "order_submitted": False,
            }
        elif command == "enable":
            if not args.enable_paper:
                raise ValueError("paper enable requires explicit --enable-paper")
            config = load_paper_config(args.config)
            payload = registry.session_payload(args.session_id)
            expected = {
                "code_version": PACKAGE_VERSION,
                "config_hash": config.config_hash,
                "data_revision": args.data_revision,
                "calendar_version": args.calendar_version,
            }
            if any(payload.get(key) != value for key, value in expected.items()):
                raise ValueError("paper enable identity does not match stored session")
            if registry.current_state(args.session_id) is not RuntimeState.SHADOW:
                raise ValueError("paper enable requires SHADOW state")
            registry.transition(
                args.session_id,
                RuntimeState.PAPER_ENABLED,
                now,
                "EXPLICIT_OPERATOR_ENABLE",
            )
            result = {
                "session_id": args.session_id,
                "state": RuntimeState.PAPER_ENABLED,
                "external_submission_enabled": False,
            }
        elif command == "status":
            result = {"session_id": args.session_id,
                      "state": registry.current_state(args.session_id)}
        elif command == "halt":
            state = registry.current_state(args.session_id)
            mode = _mode(registry, args.session_id)
            if state is not RuntimeState.HALTED:
                PaperRuntime(registry, args.session_id, mode,
                             InternalSimulatorAdapter()).halt(now, "MANUAL")
            result = {"session_id": args.session_id, "state": RuntimeState.HALTED}
        elif command == "drain":
            mode = _mode(registry, args.session_id)
            PaperRuntime(registry, args.session_id, mode, InternalSimulatorAdapter()).drain(now)
            result = {"session_id": args.session_id, "state": RuntimeState.STOPPED}
        elif command == "reconcile":
            mode = _mode(registry, args.session_id)
            reconciliation = PaperRuntime(
                registry, args.session_id, mode, InternalSimulatorAdapter()
            ).reconcile(now)
            result = {"session_id": args.session_id, "matched": reconciliation.matched}
        elif command == "report":
            state = registry.current_state(args.session_id)
            counts: dict[str, int] = {}
            for table in (
                "paper_intents", "paper_adapter_events", "paper_reconciliations",
                "paper_incidents", "paper_checkpoints", "paper_heartbeats",
                "paper_orders", "paper_fills",
            ):
                row = repository.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (args.session_id,)
                ).fetchone()
                counts[table] = 0 if row is None else int(row[0])
            body = f"# Paper runtime report: {args.session_id}\n\n- state: `{state.value}`\n"
            body += "- authority: `PHASE_1_RULES_ONLY`\n- external broker: `NONE`\n"
            body += "".join(f"- {key}: `{counts[key]}`\n" for key in sorted(counts))
            Path(args.output).write_text(body, encoding="utf-8", newline="\n")
            registry.insert_report(
                args.session_id, now, {"output": str(args.output), "counts": counts, "state": state}
            )
            result = {"session_id": args.session_id, "output": args.output}
        else:
            raise ValueError(f"unsupported paper command: {command}")
    print(canonical_json(result))
    return 0


def _mode(registry: PaperRegistry, session_id: str) -> PaperMode:
    payload = registry.session_payload(session_id)
    return PaperMode(str(payload["mode"]))
