"""Explicit sandbox-only Webull CLI."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

from trading_system.config import load_config
from trading_system.domain import TradePlan
from trading_system.market_data import XNYSCalendar
from trading_system.paper import InternalSimulatorAdapter, PaperMode, PaperRegistry, PaperRuntime
from trading_system.persistence import SQLiteRepository
from trading_system.risk import normalized_units
from trading_system.serialization import canonical_hash, canonical_json
from trading_system.webull.case1 import exact_case1_order
from trading_system.webull.case2 import (
    INITIAL_STOP,
    case2_readiness,
    exact_case2_order,
)
from trading_system.webull.config import load_webull_config
from trading_system.webull.exit_config import (
    load_exit_capabilities,
    load_exit_config,
)
from trading_system.webull.exit_registry import WebullExitRegistry
from trading_system.webull.exit_service import create_exit_authorization, environment_gate
from trading_system.webull.mapping import map_stock_order
from trading_system.webull.market_data import (
    WebullMarketDataNormalizer,
    WebullShadowDataService,
)
from trading_system.webull.operator import (
    Case1CancelRecovery,
    Case1RecoveryCaptureFinalizer,
    Case1StatusInspector,
    case1_cancel_confirmation,
    case1_order_matches,
)
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.security import load_credentials, submission_enabled
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.session import core_session_status
from trading_system.webull.smoke import (
    SmokeCase,
    load_smoke_capture,
    load_smoke_config,
    load_smoke_review,
    smoke_plan,
)
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import (
    OfficialSdkWebullCase1Transport,
    OfficialSdkWebullCase2Transport,
    OfficialSdkWebullMarketDataSource,
    OfficialSdkWebullTransport,
    WebullTransport,
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
    for name in ("reconcile-orders", "recover-orders"):
        parser = actions.add_parser(name)
        parser.add_argument("--database", required=True)
        parser.add_argument("--session-id", required=True)
        parser.add_argument("--config", required=True)
        parser.add_argument("--thresholds", required=True)
        parser.add_argument(
            "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
        )
        parser.add_argument("--allow-network-read", action="store_true")
    submit = actions.add_parser("submit-stock")
    submit.add_argument("--database", required=True)
    submit.add_argument("--session-id", required=True)
    submit.add_argument("--intent-id", required=True)
    submit.add_argument("--config", required=True)
    submit.add_argument("--thresholds", required=True)
    submit.add_argument("--exit-config", required=True)
    submit.add_argument("--exit-capabilities", required=True)
    submit.add_argument(
        "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
    )
    submit.add_argument("--enable-sandbox-submission", action="store_true")
    order_report = actions.add_parser("order-report")
    order_report.add_argument("--database", required=True)
    order_report.add_argument("--session-id", required=True)
    order_report.add_argument("--config", required=True)
    position_report = actions.add_parser("position-report")
    position_report.add_argument("--database", required=True)
    position_report.add_argument("--session-id", required=True)
    position_report.add_argument("--config", required=True)
    verify_exit = actions.add_parser("verify-exit-config")
    verify_exit.add_argument("--config", required=True)
    verify_exit.add_argument("--exit-config", required=True)
    verify_exit.add_argument("--exit-capabilities", required=True)
    arm_exits = actions.add_parser("arm-exits")
    arm_exits.add_argument("--database", required=True)
    arm_exits.add_argument("--session-id", required=True)
    arm_exits.add_argument("--config", required=True)
    arm_exits.add_argument("--thresholds", required=True)
    arm_exits.add_argument("--exit-config", required=True)
    arm_exits.add_argument("--exit-capabilities", required=True)
    arm_exits.add_argument(
        "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
    )
    arm_exits.add_argument("--allow-network-read", action="store_true")
    arm_exits.add_argument("--enable-sandbox-exits", action="store_true")
    smoke_plan_parser = actions.add_parser("smoke-plan")
    smoke_plan_parser.add_argument("--config", required=True)
    smoke_plan_parser.add_argument("--smoke-config", required=True)
    import_capture = actions.add_parser("import-smoke-capture")
    import_capture.add_argument("--database", required=True)
    import_capture.add_argument("--session-id", required=True)
    import_capture.add_argument("--config", required=True)
    import_capture.add_argument("--smoke-config", required=True)
    import_capture.add_argument("--capture", required=True)
    import_review = actions.add_parser("import-smoke-review")
    import_review.add_argument("--database", required=True)
    import_review.add_argument("--session-id", required=True)
    import_review.add_argument("--config", required=True)
    import_review.add_argument("--capture-id", required=True)
    import_review.add_argument("--review", required=True)
    smoke_status = actions.add_parser("smoke-status")
    smoke_status.add_argument("--database", required=True)
    smoke_status.add_argument("--session-id", required=True)
    smoke_status.add_argument("--config", required=True)
    smoke_status.add_argument("--smoke-config", required=True)
    smoke_preflight = actions.add_parser("smoke-case1-preflight")
    smoke_preflight.add_argument("--database", required=True)
    smoke_preflight.add_argument("--session-id", required=True)
    smoke_preflight.add_argument("--config", required=True)
    smoke_preflight.add_argument("--smoke-config", required=True)
    smoke_preflight.add_argument(
        "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
    )
    smoke_preflight.add_argument("--allow-network-read", action="store_true")
    open_orders = actions.add_parser("open-orders")
    open_orders.add_argument("--database", required=True)
    open_orders.add_argument("--session-id", required=True)
    open_orders.add_argument("--config", required=True)
    open_orders.add_argument(
        "--account-class", choices=("INDIVIDUAL_MARGIN", "INDIVIDUAL_CASH")
    )
    open_orders.add_argument("--allow-network-read", action="store_true")
    case1_status = actions.add_parser("case1-status")
    case1_status.add_argument("--database", required=True)
    case1_status.add_argument("--session-id", required=True)
    case1_status.add_argument("--config", required=True)
    case1_status.add_argument("--allow-network-read", action="store_true")
    case2_seed_preflight = actions.add_parser("case2-seed-preflight")
    case2_seed_preflight.add_argument("--database", required=True)
    case2_seed_preflight.add_argument("--session-id", required=True)
    case2_seed_preflight.add_argument("--config", required=True)
    case2_seed_preflight.add_argument("--allow-network-read", action="store_true")
    finalize_case1 = actions.add_parser("finalize-case1-recovery")
    finalize_case1.add_argument("--database", required=True)
    finalize_case1.add_argument("--session-id", required=True)
    finalize_case1.add_argument("--config", required=True)
    finalize_case1.add_argument("--smoke-config", required=True)
    cancel_case1 = actions.add_parser("cancel-case1-order")
    cancel_case1.add_argument("--database", required=True)
    cancel_case1.add_argument("--session-id", required=True)
    cancel_case1.add_argument("--config", required=True)
    cancel_case1.add_argument("--confirmation", required=True)
    cancel_case1.add_argument("--allow-network-read", action="store_true")
    cancel_case1.add_argument("--enable-sandbox-cancel", action="store_true")


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


def _exit_authorization_check(
    repository: SQLiteRepository,
    session_id: str,
    config_path: str,
    capabilities_path: str,
) -> Callable[[datetime], bool]:
    exit_config = load_exit_config(config_path)
    capabilities = load_exit_capabilities(capabilities_path)
    registry = WebullExitRegistry(repository)
    return lambda at: capabilities.approved and registry.valid_exit_authorization(
        session_id, exit_config.config_hash, capabilities.capability_hash, at
    )


def handle_webull(args: argparse.Namespace) -> int:
    config = load_webull_config(args.config)
    if args.webull_command == "verify-config":
        result: dict[str, object] = {
            "config_hash": config.config_hash,
            "environment": "SANDBOX",
            "network_used": False,
        }
    elif args.webull_command == "smoke-plan":
        smoke_config = load_smoke_config(args.smoke_config)
        result = dict(smoke_plan(smoke_config))
    elif args.webull_command == "import-smoke-capture":
        smoke_config = load_smoke_config(args.smoke_config)
        capture = load_smoke_capture(args.capture, smoke_config)
        if capture.session_id != args.session_id:
            raise ValueError("smoke capture belongs to another session")
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            inserted = WebullSmokeRegistry(repository).insert_capture(capture)
        result = {
            "session_id": args.session_id,
            "capture_id": capture.capture_id,
            "case_id": capture.case,
            "capture_hash": capture.capture_hash,
            "inserted": inserted,
            "review_status": "PENDING_REVIEW",
            "network_used": False,
            "broker_write_performed": False,
            "automatic_manifest_promotion": False,
        }
    elif args.webull_command == "import-smoke-review":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = WebullSmokeRegistry(repository)
            capture = registry.capture(args.capture_id)
            if capture.session_id != args.session_id:
                raise ValueError("smoke capture belongs to another session")
            review = load_smoke_review(args.review, capture)
            inserted = registry.insert_review(review)
        result = {
            "session_id": args.session_id,
            "capture_id": capture.capture_id,
            "review_id": review.review_id,
            "verdict": review.verdict,
            "inserted": inserted,
            "network_used": False,
            "broker_write_performed": False,
            "automatic_manifest_promotion": False,
        }
    elif args.webull_command == "smoke-status":
        smoke_config = load_smoke_config(args.smoke_config)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = WebullSmokeRegistry(repository)
            captures = registry.status(args.session_id)
            passed = registry.passed_cases(args.session_id)
        result = {
            "session_id": args.session_id,
            "required_cases": smoke_config.cases,
            "captures": captures,
            "passed_cases": passed,
            "all_cases_passed": passed == smoke_config.cases,
            "official_exit_transport_enabled": False,
            "automatic_manifest_promotion": False,
            "network_used": False,
            "broker_write_performed": False,
        }
    elif args.webull_command == "smoke-case1-preflight":
        if not args.allow_network_read:
            raise ValueError("case-1 preflight requires explicit read-only network permission")
        smoke_config = load_smoke_config(args.smoke_config)
        credentials = load_credentials()
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            service = WebullSandboxService(
                args.session_id, credentials,
                OfficialSdkWebullTransport(config, credentials),
                WebullRegistry(repository), PaperRegistry(repository),
            )
            verification = service.verify_account(
                datetime.now(UTC), account_class=args.account_class
            )
            smoke_positions, open_order_count = service.smoke_position_preflight(
                datetime.now(UTC)
            )
        long_positions = tuple(
            {"symbol": symbol, "quantity": quantity}
            for symbol, quantity in smoke_positions if quantity > 0
        )
        result = {
            "session_id": args.session_id,
            "verification_id": verification.verification_id,
            "case_id": smoke_config.cases[0],
            "long_positions": long_positions,
            "open_order_count": open_order_count,
            "case1_ready": len(long_positions) == 1 and open_order_count == 0,
            "environment": "SANDBOX",
            "network_used": True,
            "network_mode": "READ_ONLY",
            "broker_write_performed": False,
            "official_exit_transport_enabled": False,
        }
    elif args.webull_command == "open-orders":
        if not args.allow_network_read:
            raise ValueError("open-orders requires explicit read-only network permission")
        credentials = load_credentials()
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            service = WebullSandboxService(
                args.session_id,
                credentials,
                OfficialSdkWebullTransport(config, credentials),
                WebullRegistry(repository),
                PaperRegistry(repository),
            )
            verification = service.verify_account(
                datetime.now(UTC), account_class=args.account_class
            )
            orders = service.sandbox_open_orders(datetime.now(UTC))
        expected = exact_case1_order(args.session_id)
        exact_match = tuple(
            item for item in orders if case1_order_matches(item, expected)
        )
        result = {
            "session_id": args.session_id,
            "verification_id": verification.verification_id,
            "orders": orders,
            "open_order_count": len(orders),
            "case1_exact_match": len(exact_match) == 1,
            "case1_cancel_confirmation": (
                case1_cancel_confirmation(args.session_id)
                if len(exact_match) == 1 else None
            ),
            "environment": "SANDBOX",
            "network_mode": "READ_ONLY",
            "broker_write_performed": False,
        }
    elif args.webull_command == "cancel-case1-order":
        if not args.allow_network_read:
            raise ValueError("Case-1 cancellation requires pre-write network reads")
        if not args.enable_sandbox_cancel:
            raise ValueError("Case-1 cancellation requires explicit CLI enablement")
        if os.environ.get("WEBULL_ENVIRONMENT", "").upper() != "SANDBOX":
            raise ValueError("WEBULL_ENVIRONMENT must be SANDBOX")
        if os.environ.get("WEBULL_SANDBOX_CANCEL_ENABLED", "") != "true":
            raise ValueError("WEBULL_SANDBOX_CANCEL_ENABLED must equal true")
        credentials = load_credentials()
        case1_transport = OfficialSdkWebullCase1Transport(
            args.session_id, config, credentials
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            registry = WebullSmokeRegistry(repository)
            service = WebullSandboxService(
                args.session_id,
                credentials,
                cast(WebullTransport, case1_transport),
                registry,
                PaperRegistry(repository),
            )
            cancellation = Case1CancelRecovery(
                args.session_id,
                service,
                case1_transport,
                registry,
                exact_case1_order(args.session_id),
            ).run(args.confirmation)
        result = {
            "session_id": args.session_id,
            "client_order_id": cancellation.client_order_id,
            "prior_status": cancellation.prior_status,
            "final_status": cancellation.final_status,
            "cancel_requested": cancellation.cancel_requested,
            "environment": "SANDBOX",
            "broker_write_performed": cancellation.cancel_requested,
            "automatic_retry": False,
        }
    elif args.webull_command == "case1-status":
        if not args.allow_network_read:
            raise ValueError("Case-1 status requires explicit read-only network permission")
        credentials = load_credentials()
        case1_transport = OfficialSdkWebullCase1Transport(
            args.session_id, config, credentials
        )
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            service = WebullSandboxService(
                args.session_id,
                credentials,
                cast(WebullTransport, case1_transport),
                WebullRegistry(repository),
                PaperRegistry(repository),
            )
            status = Case1StatusInspector(
                args.session_id,
                service,
                case1_transport,
                exact_case1_order(args.session_id),
            ).run()
        result = {
            "session_id": args.session_id,
            "client_order_id": status.client_order_id,
            "detail_status": status.detail_status,
            "aapl_position_quantity": status.aapl_position_quantity,
            "open_order_count": status.open_order_count,
            "exact_order_open": status.exact_order_open,
            "assessment": status.assessment,
            "environment": "SANDBOX",
            "network_mode": "READ_ONLY",
            "broker_write_performed": False,
        }
    elif args.webull_command == "case2-seed-preflight":
        if not args.allow_network_read:
            raise ValueError(
                "Case-2 seed preflight requires explicit read-only network permission"
            )
        now = datetime.now(UTC)
        core_session = core_session_status(now, XNYSCalendar())
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            smoke_registry = WebullSmokeRegistry(repository)
            case1_passed = (
                SmokeCase.LONG_STOP_LIFECYCLE
                in smoke_registry.passed_cases(args.session_id)
            )
            try:
                smoke_registry.latest_envelope_evidence(
                    args.session_id, "SMOKE_CASE2_SEED_PLACE_STARTED"
                )
            except KeyError:
                write_boundary_crossed = False
            else:
                write_boundary_crossed = True
            if not case1_passed or not core_session.is_open:
                result = {
                    "session_id": args.session_id,
                    "case1_passed": case1_passed,
                    "write_boundary_crossed": write_boundary_crossed,
                    "xnys_core_session_open": core_session.is_open,
                    "next_eligible_open": (
                        None
                        if core_session.next_open is None
                        else core_session.next_open.isoformat()
                    ),
                    "seed_ready": False,
                    "replacement_ready": False,
                    "network_used": False,
                    "network_mode": "READ_ONLY",
                    "broker_write_performed": False,
                }
            else:
                credentials = load_credentials()
                case2_transport = OfficialSdkWebullCase2Transport(
                    args.session_id, config, credentials
                )
                service = WebullSandboxService(
                    args.session_id,
                    credentials,
                    cast(WebullTransport, case2_transport),
                    smoke_registry,
                    PaperRegistry(repository),
                )
                verification = service.verify_account(
                    now, account_class="INDIVIDUAL_MARGIN"
                )
                sandbox_positions = service.sandbox_positions(datetime.now(UTC))
                orders = service.sandbox_open_orders(datetime.now(UTC))
                expected = exact_case2_order(args.session_id, INITIAL_STOP)
                seed_ready, replacement_ready = case2_readiness(
                    sandbox_positions,
                    orders,
                    expected,
                    write_boundary_crossed=write_boundary_crossed,
                )
                exact_position = sandbox_positions == (("AAPL", 1),)
                result = {
                    "session_id": args.session_id,
                    "verification_id": verification.verification_id,
                    "case1_passed": True,
                    "write_boundary_crossed": write_boundary_crossed,
                    "xnys_core_session_open": True,
                    "aapl_position_quantity": (
                        1
                        if exact_position
                        else dict(sandbox_positions).get("AAPL", 0)
                    ),
                    "open_order_count": len(orders),
                    "exact_initial_stop_open": replacement_ready,
                    "seed_ready": seed_ready,
                    "replacement_ready": replacement_ready,
                    "network_used": True,
                    "network_mode": "READ_ONLY",
                    "broker_write_performed": False,
                }
    elif args.webull_command == "finalize-case1-recovery":
        smoke_config = load_smoke_config(args.smoke_config)
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            capture, inserted = Case1RecoveryCaptureFinalizer(
                args.session_id,
                WebullSmokeRegistry(repository),
                smoke_config,
                exact_case1_order(args.session_id),
            ).run()
        result = {
            "session_id": args.session_id,
            "capture_id": capture.capture_id,
            "capture_hash": capture.capture_hash,
            "case_id": capture.case,
            "inserted": inserted,
            "review_status": "PENDING_REVIEW",
            "network_used": False,
            "broker_write_performed": False,
            "automatic_manifest_promotion": False,
        }
    elif args.webull_command == "verify-exit-config":
        exit_config = load_exit_config(args.exit_config)
        capabilities = load_exit_capabilities(args.exit_capabilities)
        result = {
            "config_hash": exit_config.config_hash,
            "capability_hash": capabilities.capability_hash,
            "capabilities_approved": capabilities.approved,
            "official_exit_transport_enabled": False,
            "environment": "SANDBOX",
            "network_used": False,
        }
    elif args.webull_command == "position-report":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            exit_registry = WebullExitRegistry(repository)
            positions = []
            for position in exit_registry.positions(args.session_id):
                latest_event = exit_registry.latest_position_event(
                    position.managed_position_id
                )
                stop = exit_registry.latest_stop(position.managed_position_id)
                positions.append({
                    "managed_position_id": position.managed_position_id,
                    "symbol": position.symbol,
                    "direction": position.direction,
                    "state": None if latest_event is None else latest_event.state,
                    "remaining_quantity": (
                        position.remaining_quantity
                        if latest_event is None else latest_event.remaining_quantity
                    ),
                    "protective_client_order_id": (
                        None if stop is None else stop.client_order_id
                    ),
                    "adjusted_stop": None if stop is None else stop.adjusted_stop,
                })
            result = {
                "session_id": args.session_id,
                "positions": tuple(positions),
                "unresolved_actions": exit_registry.unresolved_actions(args.session_id),
                "environment": "SANDBOX",
                "official_exit_transport_enabled": False,
                "network_used": False,
            }
    elif args.webull_command == "arm-exits":
        if not args.allow_network_read:
            raise ValueError("exit arming requires explicit read-only network permission")
        exit_config = load_exit_config(args.exit_config)
        capabilities = load_exit_capabilities(args.exit_capabilities)
        if not capabilities.approved:
            raise ValueError("Phase 3D official writes remain locked pending 3D-5 review")
        credentials = load_credentials()
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            paper = PaperRegistry(repository)
            exit_registry = WebullExitRegistry(repository)
            transport = OfficialSdkWebullTransport(config, credentials)
            read_service = WebullSandboxService(
                args.session_id, credentials, transport, exit_registry, paper
            )
            occurred_at = datetime.now(UTC)
            read_service.verify_account(occurred_at, account_class=args.account_class)
            reconciliation = read_service.reconcile(
                _risk_budget(args.thresholds), datetime.now(UTC)
            )
            authorization = create_exit_authorization(
                exit_registry,
                args.session_id,
                exit_config,
                capabilities,
                datetime.now(UTC),
                reconciliation.reconciliation_id,
                environment_enabled=environment_gate(
                    str(exit_config.values["exit_environment_flag"])
                ),
                cli_enabled=args.enable_sandbox_exits,
            )
            result = {
                "session_id": args.session_id,
                "authorization_id": authorization.authorization_id,
                "expires_at": authorization.expires_at,
                "environment": "SANDBOX",
                "order_submitted": False,
            }
    elif args.webull_command == "order-report":
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            paper = PaperRegistry(repository)
            order_registry = WebullRegistry(repository)
            counts: dict[str, int] = {}
            for table in (
                "webull_order_previews",
                "webull_entry_releases",
                "webull_submission_events",
                "webull_client_orders",
                "webull_broker_events",
                "webull_executions",
                "webull_reconciliations",
                "webull_transport_incidents",
            ):
                row = repository.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE session_id = ?",
                    (args.session_id,),
                ).fetchone()
                counts[table] = 0 if row is None else int(row[0])
            latest_reconciliation = order_registry.latest_reconciliation(args.session_id)
            result = {
                "session_id": args.session_id,
                "state": paper.current_state(args.session_id),
                "counts": counts,
                "unresolved_intent_ids": order_registry.unresolved_submission_intents(
                    args.session_id
                ),
                "latest_reconciliation": latest_reconciliation,
                "environment": "SANDBOX",
                "production_enabled": False,
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
        "preview-stock", "reconcile-orders", "recover-orders", "submit-stock",
    }:
        if args.webull_command == "preview-stock":
            if not args.allow_network_preview:
                raise ValueError("Webull preview requires explicit preview-only permission")
        elif args.webull_command == "submit-stock":
            if not args.enable_sandbox_submission:
                raise ValueError("Webull submission requires explicit CLI enablement")
        elif not args.allow_network_read:
            raise ValueError("read-only Webull network verification requires explicit permission")
        credentials = load_credentials()
        with SQLiteRepository(args.database) as repository:
            repository.migrate()
            if args.webull_command in {
                "preview-stock", "reconcile-orders", "recover-orders", "submit-stock"
            }:
                paper = PaperRegistry(repository)
                risk_budget = _risk_budget(args.thresholds)
                streaming = config.values["streaming"]
                if not isinstance(streaming, dict):
                    raise TypeError("validated Webull streaming config must be a mapping")
                reconciliation_age = streaming["reconciliation_interval_seconds"]
                if not isinstance(reconciliation_age, int):
                    raise TypeError("validated reconciliation interval must be an integer")
                stock_order = config.values["stock_order"]
                if not isinstance(stock_order, dict):
                    raise TypeError("validated Webull stock-order config must be a mapping")
                max_gap_adr = Decimal(str(stock_order["max_gap_adr"]))
                max_release_lateness = stock_order["max_release_lateness_seconds"]
                if not isinstance(max_release_lateness, int):
                    raise TypeError("validated release lateness must be an integer")
                service = WebullSandboxService(
                    args.session_id, credentials,
                    OfficialSdkWebullTransport(config, credentials),
                    WebullRegistry(repository), paper,
                    reconciliation_max_age_seconds=reconciliation_age,
                    max_gap_adr=max_gap_adr,
                    max_release_lateness_seconds=max_release_lateness,
                    exit_authorization_check=(
                        None
                        if args.webull_command != "submit-stock"
                        else _exit_authorization_check(
                            repository,
                            args.session_id,
                            args.exit_config,
                            args.exit_capabilities,
                        )
                    ),
                )
                operation_time = datetime.now(UTC)
                verification = service.verify_account(
                    operation_time, account_class=args.account_class
                )
                if args.webull_command == "preview-stock":
                    intent = paper.load_intent(args.intent_id)
                    if intent.session_id != args.session_id:
                        raise ValueError("Webull preview intent belongs to another paper session")
                    bounds = XNYSCalendar().bounds(intent.scheduled_open.date())
                    if bounds is None or intent.scheduled_open != bounds[0]:
                        raise ValueError("Webull preview intent is not scheduled for an XNYS open")
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
                elif args.webull_command == "reconcile-orders":
                    reconciliation = service.reconcile(risk_budget, datetime.now(UTC))
                    result = {
                        "session_id": args.session_id,
                        "verification_id": verification.verification_id,
                        "reconciliation_id": reconciliation.reconciliation_id,
                        "matched": reconciliation.matched,
                        "differences": reconciliation.differences,
                        "environment": "SANDBOX",
                        "order_submitted": False,
                    }
                elif args.webull_command == "recover-orders":
                    recovered = service.recover(risk_budget, datetime.now(UTC))
                    reconciliation = service.reconcile(risk_budget, datetime.now(UTC))
                    result = {
                        "session_id": args.session_id,
                        "verification_id": verification.verification_id,
                        "recovered_client_order_ids": tuple(
                            item.client_order_id for item in recovered
                        ),
                        "matched": reconciliation.matched,
                        "environment": "SANDBOX",
                        "order_submitted": False,
                    }
                else:
                    order = service.order_for_intent(args.intent_id, risk_budget)
                    reconciliation = service.reconcile(risk_budget, datetime.now(UTC))
                    item = service.submit(
                        args.intent_id,
                        order,
                        datetime.now(UTC),
                        environment_enabled=submission_enabled(
                            str(config.values["submission_environment_flag"])
                        ),
                        cli_enabled=args.enable_sandbox_submission,
                    )
                    result = {
                        "session_id": args.session_id,
                        "intent_id": args.intent_id,
                        "verification_id": verification.verification_id,
                        "reconciliation_id": reconciliation.reconciliation_id,
                        "client_order_id": item.client_order_id,
                        "broker_order_id": item.broker_order_id,
                        "status": item.status,
                        "environment": "SANDBOX",
                        "order_submitted": True,
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
