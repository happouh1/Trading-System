"""Explicit sandbox-only Webull CLI."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from trading_system.paper import PaperRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json
from trading_system.webull.config import load_webull_config
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.security import load_credentials
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.transport import OfficialSdkWebullTransport


def configure_webull_parser(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    webull = commands.add_parser("webull")
    actions = webull.add_subparsers(dest="webull_command", required=True)
    verify_config = actions.add_parser("verify-config")
    verify_config.add_argument("--config", required=True)
    verify_account = actions.add_parser("verify-account")
    verify_account.add_argument("--database", required=True)
    verify_account.add_argument("--session-id", required=True)
    verify_account.add_argument("--config", required=True)
    verify_account.add_argument("--allow-network-read", action="store_true")
    verify_account.add_argument(
        "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
    )
    discover = actions.add_parser("discover-accounts")
    discover.add_argument("--database", required=True)
    discover.add_argument("--session-id", required=True)
    discover.add_argument("--config", required=True)
    discover.add_argument("--allow-network-read", action="store_true")


def handle_webull(args: argparse.Namespace) -> int:
    config = load_webull_config(args.config)
    if args.webull_command == "verify-config":
        result: dict[str, object] = {
            "config_hash": config.config_hash,
            "environment": "SANDBOX",
            "network_used": False,
        }
    elif args.webull_command in {"verify-account", "discover-accounts"}:
        if not args.allow_network_read:
            raise ValueError("read-only Webull network verification requires explicit permission")
        credentials = load_credentials()
        transport = OfficialSdkWebullTransport(config, credentials)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            service = WebullSandboxService(
                args.session_id, credentials, transport, WebullRegistry(repository),
                PaperRegistry(repository),
            )
            if args.webull_command == "discover-accounts":
                accounts = service.discover_accounts(datetime.now(UTC))
                result = {"session_id": args.session_id, "accounts": accounts,
                          "environment": "SANDBOX", "read_only": True}
            else:
                verification = service.verify_account(
                    datetime.now(UTC), account_class=args.account_class
                )
                result = {
                    "session_id": args.session_id,
                    "verification_id": verification.verification_id,
                    "account_count": verification.account_count,
                    "environment": "SANDBOX",
                }
    else:
        raise ValueError(f"unsupported Webull command: {args.webull_command}")
    print(canonical_json(result))
    return 0
