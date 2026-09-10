"""Command-line entry point for the Phase 9G local operator home."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_system.desktop.launcher import inspect_desktop_launcher, load_desktop_launch_config
from trading_system.serialization import canonical_json


def configure_desktop_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    desktop = commands.add_parser("desktop")
    actions = desktop.add_subparsers(dest="desktop_command", required=True)
    for name in ("status", "home"):
        command = actions.add_parser(name)
        command.add_argument("--config", required=True)
        command.add_argument("--project-root", default=".")


def handle_desktop(args: argparse.Namespace) -> int:
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
