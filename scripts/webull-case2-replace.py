"""One-shot exact Webull sandbox Case-2 stop-replacement evidence capture."""

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
from trading_system.webull.case1 import Case1AmbiguousError, Case1IncompleteError
from trading_system.webull.case2 import Case2Runner
from trading_system.webull.config import API_SANDBOX_HOST, load_webull_config
from trading_system.webull.registry import WebullRegistry
from trading_system.webull.security import load_credentials
from trading_system.webull.service import WebullSandboxService
from trading_system.webull.session import core_session_status
from trading_system.webull.smoke import SmokeCase, load_smoke_config
from trading_system.webull.smoke_registry import WebullSmokeRegistry
from trading_system.webull.transport import (
    OfficialSdkWebullCase2Transport,
    WebullTransport,
)

CONFIRMATION = "REPLACE-SELL-1-AAPL-STOP-1.00-TO-1.01-GTC-CORE-WEBULL-SANDBOX"


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
        raise ValueError("exact Case-2 sandbox confirmation is required")
    if os.environ.get("WEBULL_ENVIRONMENT", "").upper() != "SANDBOX":
        raise ValueError("WEBULL_ENVIRONMENT must be SANDBOX")
    config = load_webull_config(Path(args.config).resolve())
    if config.values["api_endpoint"] != API_SANDBOX_HOST:
        raise ValueError("only the official Webull sandbox endpoint is permitted")
    smoke_config = load_smoke_config(Path(args.smoke_config).resolve())
    with SQLiteRepository(args.database) as repository:
        repository.migrate()
        smoke_registry = WebullSmokeRegistry(repository)
        if SmokeCase.LONG_STOP_LIFECYCLE not in smoke_registry.passed_cases(args.session_id):
            print(json.dumps({
                "broker_write_performed": False,
                "environment": "SANDBOX",
                "reason": "CASE1_PASS_REVIEW_REQUIRED",
                "session_id": args.session_id,
            }, sort_keys=True))
            return 4
        session = core_session_status(datetime.now(UTC), XNYSCalendar())
        if not session.is_open:
            print(json.dumps({
                "broker_write_performed": False,
                "environment": "SANDBOX",
                "next_eligible_open": None
                if session.next_open is None else session.next_open.isoformat(),
                "reason": "XNYS_CORE_SESSION_CLOSED",
                "session_id": args.session_id,
            }, sort_keys=True))
            return 4
        credentials = load_credentials()
        transport = OfficialSdkWebullCase2Transport(args.session_id, config, credentials)
        service = WebullSandboxService(
            args.session_id,
            credentials,
            cast(WebullTransport, transport),
            WebullRegistry(repository),
            PaperRegistry(repository),
        )
        try:
            result = Case2Runner(
                args.session_id, service, transport, smoke_registry, smoke_config
            ).run()
        except (Case1AmbiguousError, Case1IncompleteError) as error:
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
