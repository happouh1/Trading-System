"""One-shot exact Webull sandbox stop/detail/cancel evidence capture."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from trading_system.market_data import XNYSCalendar
from trading_system.paper import PaperRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.webull.case1 import Case1IncompleteError, Case1Runner
from trading_system.webull.config import API_SANDBOX_HOST, load_webull_config
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.security import load_credentials
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.session import core_session_status
from trading_system.webull.smoke import load_smoke_config
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import OfficialSdkWebullCase1Transport, WebullTransport

CONFIRMATION = "PLACE-CANCEL-SELL-1-AAPL-STOP-1.00-GTC-CORE-WEBULL-SANDBOX"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--smoke-config", required=True)
    parser.add_argument("--confirmation", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.confirmation != CONFIRMATION:
        raise ValueError("exact Case-1 sandbox confirmation is required")
    if os.environ.get("WEBULL_ENVIRONMENT", "").upper() != "SANDBOX":
        raise ValueError("WEBULL_ENVIRONMENT must be SANDBOX")
    config = load_webull_config(Path(args.config).resolve())
    if config.values["api_endpoint"] != API_SANDBOX_HOST:
        raise ValueError("only the official Webull sandbox endpoint is permitted")
    smoke_config = load_smoke_config(Path(args.smoke_config).resolve())

    session = core_session_status(datetime.now(UTC), XNYSCalendar())
    if not session.is_open:
        print(json.dumps({
            "environment": "SANDBOX",
            "network_used": False,
            "next_eligible_open": None
            if session.next_open is None else session.next_open.isoformat(),
            "reason": "XNYS_CORE_SESSION_CLOSED",
            "write_performed": False,
        }, sort_keys=True))
        return 4

    credentials = load_credentials()
    transport = OfficialSdkWebullCase1Transport(args.session_id, config, credentials)
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        base_registry = WebullRegistry(repository)
        smoke_registry = WebullSmokeRegistry(repository)
        service = WebullSandboxService(
            args.session_id,
            credentials,
            cast(WebullTransport, transport),
            base_registry,
            PaperRegistry(repository),
        )
        try:
            result = Case1Runner(
                args.session_id, service, transport, smoke_registry, smoke_config
            ).run()
        except Case1IncompleteError as error:
            print(json.dumps({
                "capture_created": False,
                "environment": "SANDBOX",
                "halted": True,
                "reason": str(error),
                "session_id": args.session_id,
            }, sort_keys=True))
            return 5
        print(json.dumps({
            "automatic_manifest_promotion": False,
            "capture_id": result.capture.capture_id,
            "case_id": result.capture.case.value,
            "environment": "SANDBOX",
            "general_exit_routing_enabled": False,
            "review_status": "PENDING_REVIEW",
            "session_id": args.session_id,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
