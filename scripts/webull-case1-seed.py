"""One-shot operator helper for the approved Phase 3D-5 sandbox seed position."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from trading_system.market_data import XNYSCalendar
from trading_system.paper import PaperRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.webull.config import API_SANDBOX_HOST, load_webull_config
from trading_system.webull.contracts import WebullSide, WebullStockOrder
from trading_system.webull.mapping import client_order_id
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.security import load_credentials
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.session import core_session_status
from trading_system.webull.transport import OfficialSdkWebullTransport

CONFIRMATION = "BUY-1-AAPL-IN-WEBULL-SANDBOX"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--confirmation", required=True)
    return parser


def _safe_shape(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}
    result: dict[str, object] = {"top_level_keys": sorted(payload)}
    accepted = payload.get("accepted")
    if isinstance(accepted, bool):
        result["accepted"] = accepted
    items = payload.get("items")
    if isinstance(items, (tuple, list)):
        result["item_count"] = len(items)
    return result


def main() -> int:
    args = _parser().parse_args()
    if args.confirmation != CONFIRMATION:
        raise ValueError("exact sandbox seed confirmation is required")
    if os.environ.get("WEBULL_ENVIRONMENT", "").upper() != "SANDBOX":
        raise ValueError("WEBULL_ENVIRONMENT must be SANDBOX")

    config_path = Path(args.config).resolve()
    config = load_webull_config(config_path)
    if config.values["api_endpoint"] != API_SANDBOX_HOST:
        raise ValueError("only the official Webull sandbox endpoint is permitted")

    now = datetime.now(UTC)
    session = core_session_status(now, XNYSCalendar())
    if not session.is_open:
        if session.next_open is None:
            raise ValueError("closed XNYS session has no next eligible open")
        print(json.dumps({
            "calendar": session.calendar_name,
            "calendar_version": session.calendar_version,
            "environment": "SANDBOX",
            "network_used": False,
            "next_eligible_open": session.next_open.isoformat(),
            "order_submitted": False,
            "reason": "XNYS_CORE_SESSION_CLOSED",
        }, sort_keys=True))
        return 4

    credentials = load_credentials()
    transport = OfficialSdkWebullTransport(config, credentials)
    order = WebullStockOrder(
        client_order_id(f"{args.session_id}:phase3d5:case1:seed:AAPL"),
        "AAPL",
        WebullSide.BUY,
        1,
    )

    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        registry = WebullRegistry(repository)
        service = WebullSandboxService(
            args.session_id,
            credentials,
            transport,
            registry,
            PaperRegistry(repository),
        )
        service.verify_account(now, account_class="INDIVIDUAL_MARGIN")
        positions_before, open_before = service.smoke_position_preflight(now)
        if positions_before or open_before:
            raise ValueError("sandbox seed requires zero positions and zero open orders")
        account_id = service._require_verified()

        preview = transport.preview(account_id, order)
        registry.insert_envelope(
            args.session_id, "SMOKE_SEED_PREVIEW", datetime.now(UTC), preview, order
        )
        preview_summary = {
            "status_code": preview.status_code,
            **_safe_shape(dict(preview.payload)),
        }
        if not 200 <= preview.status_code < 300:
            print(json.dumps({
                "environment": "SANDBOX",
                "preview": preview_summary,
                "order_submitted": False,
            }, sort_keys=True))
            return 2

        placed = transport.place(account_id, order)
        registry.insert_envelope(
            args.session_id, "SMOKE_SEED_PLACE", datetime.now(UTC), placed, order
        )
        print(json.dumps({
            "client_order_id": order.client_order_id,
            "environment": "SANDBOX",
            "order": {
                "order_type": "MARKET",
                "quantity": 1,
                "side": "BUY",
                "symbol": "AAPL",
                "support_trading_session": "CORE",
                "time_in_force": "DAY",
            },
            "order_submitted": 200 <= placed.status_code < 300,
            "place": {
                "status_code": placed.status_code,
                **_safe_shape(dict(placed.payload)),
            },
            "preview": preview_summary,
        }, sort_keys=True))
        return 0 if 200 <= placed.status_code < 300 else 3


if __name__ == "__main__":
    raise SystemExit(main())
