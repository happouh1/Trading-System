"""Explicit sandbox-only Webull CLI."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal

from trading_system.config import load_config
from trading_system.domain import TradePlan
from trading_system.market_data import XNYSCalendar
from trading_system.paper import InternalSimulatorAdapter, PaperMode, PaperRegistry, PaperRuntime
from trading_system.persistence import SQLiteRepository
from trading_system.risk import normalized_units
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull.config import load_webull_config
from trading_system.webull.mapping import map_stock_order
from trading_system.webull.market_data import (
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
    history.add_argument("--allow-network-read", action="store_true")
    snapshot = actions.add_parser("market-snapshot")
    snapshot.add_argument("--database", required=True)
    snapshot.add_argument("--session-id", required=True)
    snapshot.add_argument("--config", required=True)
    snapshot.add_argument("--symbols", required=True)
    snapshot.add_argument("--allow-network-read", action="store_true")
    preview = actions.add_parser("preview-stock")
    preview.add_argument("--database", required=True)
    preview.add_argument("--session-id", required=True)
    preview.add_argument("--intent-id", required=True)
    preview.add_argument("--config", required=True)
    preview.add_argument("--thresholds", required=True)
    preview.add_argument(
        "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
    )
    preview.add_argument("--allow-network-preview", action="store_true")
    candidates = actions.add_parser("preview-candidates")
    candidates.add_argument("--database", required=True)
    candidates.add_argument("--session-id", required=True)
    candidates.add_argument("--config", required=True)
    candidates.add_argument("--thresholds", required=True)
    candidates.add_argument("--as-of", required=True)


def _risk_budget(path: str) -> Decimal:
    thresholds = load_config(path)
    value = thresholds.section("risk").get("normalized_risk_budget_currency")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Phase 1 normalized risk budget is required")
    return Decimal(str(value))


def _utc_timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("--as-of must be a timezone-aware timestamp")
    return result.astimezone(UTC)


def handle_webull(args: argparse.Namespace) -> int:
    config = load_webull_config(args.config)
    if args.webull_command == "verify-config":
        result: dict[str, object] = {
            "config_hash": config.config_hash,
            "environment": "SANDBOX",
            "network_used": False,
        }
    elif args.webull_command == "preview-candidates":
        as_of = _utc_timestamp(args.as_of)
        risk_budget = _risk_budget(args.thresholds)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            paper = PaperRegistry(repository)
            webull_registry = WebullRegistry(repository)
            calendar = XNYSCalendar()
            candidates: list[dict[str, object]] = []
            for intent_id in paper.intent_ids(args.session_id):
                intent = paper.load_intent(intent_id)
                plan = intent.payload.get("trade_plan")
                if not isinstance(plan, TradePlan):
                    raise ValueError("stored preview candidate has no trade plan")
                quantity = int(normalized_units(risk_budget, plan.risk_per_unit))
                if quantity <= 0:
                    raise ValueError("stored preview candidate has zero quantity")
                order = map_stock_order(plan, intent_id, quantity)
                bounds = calendar.bounds(intent.scheduled_open.date())
                reasons: list[str] = []
                if bounds is None or intent.scheduled_open != bounds[0]:
                    reasons.append("NOT_XNYS_SESSION_OPEN")
                if intent.scheduled_open <= as_of:
                    reasons.append("SCHEDULED_OPEN_NOT_FUTURE")
                preview_status = webull_registry.preview_status(
                    args.session_id, intent_id, canonical_hash(order)
                )
                if preview_status is not None:
                    reasons.append("ALREADY_PREVIEWED")
                candidates.append({
                    "intent_id": intent_id,
                    "plan_id": plan.plan_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": order.quantity,
                    "scheduled_open": intent.scheduled_open,
                    "request_hash": canonical_hash(order),
                    "preview_status": preview_status,
                    "eligible": not reasons,
                    "reasons": tuple(reasons),
                })
        result = {
            "session_id": args.session_id,
            "as_of": as_of,
            "candidates": tuple(candidates),
            "network_used": False,
            "order_submitted": False,
            "config_hash": config.config_hash,
        }
    elif args.webull_command in {
        "verify-account", "discover-accounts", "shadow-history", "market-snapshot",
        "preview-stock",
    }:
        if args.webull_command == "preview-stock":
            if not args.allow_network_preview:
                raise ValueError("Webull preview requires explicit preview-only permission")
        elif not args.allow_network_read:
            raise ValueError("read-only Webull network verification requires explicit permission")
        credentials = load_credentials()
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            if args.webull_command == "preview-stock":
                paper = PaperRegistry(repository)
                intent = paper.load_intent(args.intent_id)
                if intent.session_id != args.session_id:
                    raise ValueError("Webull preview intent belongs to another paper session")
                bounds = XNYSCalendar().bounds(intent.scheduled_open.date())
                if bounds is None or intent.scheduled_open != bounds[0]:
                    raise ValueError("Webull preview intent is not scheduled for an XNYS open")
                risk_budget = _risk_budget(args.thresholds)
                service = WebullSandboxService(
                    args.session_id, credentials,
                    OfficialSdkWebullTransport(config, credentials),
                    WebullRegistry(repository), paper,
                )
                verification = service.verify_account(
                    datetime.now(UTC), account_class=args.account_class
                )
                order, accepted = service.preview_intent(
                    args.intent_id, risk_budget, datetime.now(UTC)
                )
                result = {
                    "session_id": args.session_id,
                    "intent_id": args.intent_id,
                    "verification_id": verification.verification_id,
                    "client_order_id": order.client_order_id,
                    "request_hash": canonical_hash(order),
                    "accepted": accepted,
                    "environment": "SANDBOX",
                    "order_submitted": False,
                }
            elif args.webull_command == "market-snapshot":
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
                ).ingest_sdk_history(response, received_at=received_at)
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
