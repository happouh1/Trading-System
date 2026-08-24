"""Explicit sandbox-only Webull CLI."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from trading_system.market_data import XNYSCalendar
from trading_system.paper import InternalSimulatorAdapter, PaperMode, PaperRegistry, PaperRuntime
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_json
from trading_system.webull.config import load_webull_config
from trading_system.webull.market_data import (
    MarketDataKind,
    WebullMarketDataNormalizer,
    WebullShadowDataService,
)
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.security import load_credentials
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.transport import (
    OfficialSdkWebullMarketDataSource,
    OfficialSdkWebullTransport,
)


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
    history = actions.add_parser("shadow-history")
    history.add_argument("--database", required=True)
    history.add_argument("--session-id", required=True)
    history.add_argument("--config", required=True)
    history.add_argument("--symbol", required=True)
    history.add_argument("--timespan", choices=("M60",), required=True)
    history.add_argument("--count", type=int, default=200)
    history.add_argument("--source-revision", required=True)
    history.add_argument("--allow-network-read", action="store_true")
    snapshot = actions.add_parser("market-snapshot")
    snapshot.add_argument("--database", required=True)
    snapshot.add_argument("--session-id", required=True)
    snapshot.add_argument("--config", required=True)
    snapshot.add_argument("--symbols", required=True)
    snapshot.add_argument("--allow-network-read", action="store_true")


def handle_webull(args: argparse.Namespace) -> int:
    config = load_webull_config(args.config)
    if args.webull_command == "verify-config":
        result: dict[str, object] = {
            "config_hash": config.config_hash,
            "environment": "SANDBOX",
            "network_used": False,
        }
    elif args.webull_command in {
        "verify-account", "discover-accounts", "shadow-history", "market-snapshot"
    }:
        if not args.allow_network_read:
            raise ValueError("read-only Webull network verification requires explicit permission")
        credentials = load_credentials()
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            if args.webull_command == "market-snapshot":
                market_source = OfficialSdkWebullMarketDataSource(config, credentials)
                symbols = tuple(
                    item.strip().upper()
                    for item in args.symbols.split(",")
                    if item.strip()
                )
                response = market_source.market_snapshot(symbols)
                WebullRegistry(repository).insert_envelope(
                    args.session_id, "MARKET_SNAPSHOT", datetime.now(UTC), response
                )
                result = {"session_id": args.session_id, "symbols": symbols,
                          "status_code": response.status_code, "read_only": True}
            elif args.webull_command == "shadow-history":
                market_source = OfficialSdkWebullMarketDataSource(config, credentials)
                if args.count <= 0 or args.count > 1200:
                    raise ValueError("Webull history count must be between 1 and 1200")
                received_at = datetime.now(UTC)
                response = market_source.historical_bars(
                    args.symbol.upper(), args.timespan, args.count
                )
                market_config = config.values["market_data"]
                if not isinstance(market_config, dict):
                    raise TypeError("validated Webull market-data config must be a mapping")
                lateness = market_config["max_completed_bar_lateness_seconds"]
                if not isinstance(lateness, int):
                    raise TypeError("validated Webull lateness must be an integer")
                runtime = PaperRuntime(
                    PaperRegistry(repository), args.session_id, PaperMode.SHADOW,
                    InternalSimulatorAdapter(), completed_bar_lateness_seconds=lateness,
                )
                bars = WebullShadowDataService(
                    args.session_id,
                    WebullMarketDataNormalizer(XNYSCalendar(), max_lateness_seconds=lateness),
                    WebullRegistry(repository), runtime,
                ).ingest(
                    response, received_at=received_at,
                    source_revision=args.source_revision, kind=MarketDataKind.HISTORICAL,
                )
                result = {"session_id": args.session_id, "bars": len(bars),
                          "environment": "SANDBOX", "read_only": True}
            elif args.webull_command == "discover-accounts":
                transport = OfficialSdkWebullTransport(config, credentials)
                service = WebullSandboxService(
                    args.session_id, credentials, transport, WebullRegistry(repository),
                    PaperRegistry(repository),
                )
                accounts = service.discover_accounts(datetime.now(UTC))
                result = {"session_id": args.session_id, "accounts": accounts,
                          "environment": "SANDBOX", "read_only": True}
            else:
                transport = OfficialSdkWebullTransport(config, credentials)
                service = WebullSandboxService(
                    args.session_id, credentials, transport, WebullRegistry(repository),
                    PaperRegistry(repository),
                )
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
