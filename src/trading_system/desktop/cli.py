"""Command-line entry point for the Phase 9G local operator home."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_system.desktop.dashboard import (
    load_desktop_dashboard_config,
    render_desktop_dashboard,
)
from trading_system.desktop.launcher import inspect_desktop_launcher, load_desktop_launch_config
from trading_system.desktop.local_status import inspect_local_operations, load_local_status_config
from trading_system.desktop.readiness import (
    assess_local_launch_readiness,
    load_launch_readiness_config,
)
from trading_system.desktop.release_audit import (
    ReleaseAuditState,
    audit_release_readiness,
    load_release_audit_config,
)
from trading_system.desktop.upgrade_plan import (
    build_local_schema_upgrade_plan,
    load_upgrade_plan_config,
)
from trading_system.desktop.upgrade_rehearsal import (
    load_upgrade_rehearsal_config,
    rehearse_schema_upgrade,
)
from trading_system.serialization import canonical_json


def configure_desktop_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    desktop = commands.add_parser("desktop")
    actions = desktop.add_subparsers(dest="desktop_command", required=True)
    for name in ("status", "home"):
        command = actions.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--project-root", default=".")
    render = actions.add_parser("render")
    render.add_argument("--config", required=True)
    render.add_argument("--project-root", default=".")
    render_status = actions.add_parser("render-status")
    render_status.add_argument("--config", required=True)
    render_status.add_argument("--project-root", default=".")
    render_readiness = actions.add_parser("render-readiness")
    render_readiness.add_argument("--config", required=True)
    render_readiness.add_argument("--project-root", default=".")
    render_upgrade = actions.add_parser("render-upgrade-plan")
    render_upgrade.add_argument("--config", required=True)
    render_upgrade.add_argument("--project-root", default=".")
    rehearse = actions.add_parser("rehearse-upgrade")
    rehearse.add_argument("--config", required=True)
    rehearse.add_argument("--project-root", default=".")
    rehearse.add_argument("--source", required=True)
    rehearse.add_argument("--source-revision", required=True)
    release_audit = actions.add_parser("release-audit")
    release_audit.add_argument("--config", required=True)
    release_audit.add_argument("--project-root", default=".")


def handle_desktop(args: argparse.Namespace) -> int:
    if args.desktop_command == "release-audit":
        assessment = audit_release_readiness(
            load_release_audit_config(args.config), project_root=args.project_root
        )
        print(canonical_json(assessment))
        return (
            0
            if assessment.state
            is ReleaseAuditState.READY_FOR_PROSPECTIVE_SANDBOX_BURN_IN
            else 1
        )
    if args.desktop_command == "rehearse-upgrade":
        result = rehearse_schema_upgrade(
            load_upgrade_rehearsal_config(args.config),
            project_root=args.project_root,
            source_path=args.source,
            source_revision=args.source_revision,
        )
        print(canonical_json(result))
        return 0
    if args.desktop_command == "render-upgrade-plan":
        root = Path(args.project_root).resolve()
        upgrade_config = load_upgrade_plan_config(args.config)
        readiness_path = upgrade_config.values["readiness_config"]
        if not isinstance(readiness_path, str):
            raise TypeError("validated Phase 9K readiness config path must be text")
        readiness_config = load_launch_readiness_config(root / readiness_path)
        local_path = readiness_config.values["local_status_config"]
        if not isinstance(local_path, str):
            raise TypeError("validated Phase 9J local status config path must be text")
        local_config = load_local_status_config(root / local_path)
        dashboard_path = local_config.values["dashboard_config"]
        if not isinstance(dashboard_path, str):
            raise TypeError("validated Phase 9I dashboard config path must be text")
        dashboard_config = load_desktop_dashboard_config(root / dashboard_path)
        operator_path = dashboard_config.values["operator_config"]
        if not isinstance(operator_path, str):
            raise TypeError("validated Phase 9H operator config path must be text")
        status = inspect_desktop_launcher(
            load_desktop_launch_config(root / operator_path), project_root=root
        )
        operations = inspect_local_operations(local_config, project_root=root)
        readiness = assess_local_launch_readiness(
            readiness_config, operations, project_root=root
        )
        upgrade_plan = build_local_schema_upgrade_plan(upgrade_config, project_root=root)
        artifact = render_desktop_dashboard(
            dashboard_config,
            status,
            project_root=root,
            operations=operations,
            readiness=readiness,
            upgrade_plan=upgrade_plan,
        )
        print(canonical_json(artifact))
        return 0 if status.operator_home_ready else 1
    if args.desktop_command == "render-readiness":
        root = Path(args.project_root).resolve()
        readiness_config = load_launch_readiness_config(args.config)
        local_path = readiness_config.values["local_status_config"]
        if not isinstance(local_path, str):
            raise TypeError("validated Phase 9J local status config path must be text")
        local_config = load_local_status_config(root / local_path)
        dashboard_path = local_config.values["dashboard_config"]
        if not isinstance(dashboard_path, str):
            raise TypeError("validated Phase 9I dashboard config path must be text")
        dashboard_config = load_desktop_dashboard_config(root / dashboard_path)
        operator_path = dashboard_config.values["operator_config"]
        if not isinstance(operator_path, str):
            raise TypeError("validated Phase 9H operator config path must be text")
        status = inspect_desktop_launcher(
            load_desktop_launch_config(root / operator_path), project_root=root
        )
        operations = inspect_local_operations(local_config, project_root=root)
        readiness = assess_local_launch_readiness(
            readiness_config, operations, project_root=root
        )
        artifact = render_desktop_dashboard(
            dashboard_config,
            status,
            project_root=root,
            operations=operations,
            readiness=readiness,
        )
        print(canonical_json(artifact))
        return 0 if status.operator_home_ready else 1
    if args.desktop_command == "render-status":
        root = Path(args.project_root).resolve()
        local_config = load_local_status_config(args.config)
        dashboard_path = local_config.values["dashboard_config"]
        if not isinstance(dashboard_path, str):
            raise TypeError("validated Phase 9I dashboard config path must be text")
        dashboard_config = load_desktop_dashboard_config(root / dashboard_path)
        operator_path = dashboard_config.values["operator_config"]
        if not isinstance(operator_path, str):
            raise TypeError("validated Phase 9H operator config path must be text")
        status = inspect_desktop_launcher(
            load_desktop_launch_config(root / operator_path), project_root=root
        )
        operations = inspect_local_operations(local_config, project_root=root)
        artifact = render_desktop_dashboard(
            dashboard_config, status, project_root=root, operations=operations
        )
        print(canonical_json(artifact))
        return 0 if status.operator_home_ready else 1
    if args.desktop_command == "render":
        dashboard_config = load_desktop_dashboard_config(args.config)
        root = Path(args.project_root).resolve()
        operator_path = dashboard_config.values["operator_config"]
        if not isinstance(operator_path, str):
            raise TypeError("validated Phase 9H operator config path must be text")
        operator_config = load_desktop_launch_config(root / operator_path)
        status = inspect_desktop_launcher(operator_config, project_root=root)
        artifact = render_desktop_dashboard(dashboard_config, status, project_root=root)
        print(canonical_json(artifact))
        return 0 if status.operator_home_ready else 1
    config = load_desktop_launch_config(args.config)
    status = inspect_desktop_launcher(config, project_root=args.project_root)
    if args.desktop_command == "status":
        print(canonical_json(status))
    else:
        print("Trading System - Operator Home")
        print(f"Mode: {status.mode}")
        print(f"Installation: {'READY' if status.operator_home_ready else 'NEEDS ATTENTION'}")
        if status.missing_paths:
            print(f"Missing: {', '.join(status.missing_paths)}")
        print("Trading: DISABLED")
        print("Broker writes: DISABLED")
        print("This screen does not connect to Webull or place orders.")
    return 0 if status.operator_home_ready else 1


def default_project_root() -> Path:
    return Path(__file__).parents[3]
