"""Strict sandbox-only Phase 3C configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash

API_SANDBOX_HOST = "api.sandbox.webull.com"
EVENTS_SANDBOX_HOST = "events-api.sandbox.webull.com"


@dataclass(frozen=True, slots=True)
class WebullConfig:
    values: Mapping[str, object]
    config_hash: str


def load_webull_config(path: str | Path) -> WebullConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {
        "webull_version", "sdk_version", "region_id", "api_endpoint", "events_endpoint",
        "credential_environment", "submission_environment_flag", "connect_timeout_seconds",
        "request_timeout_seconds", "automatic_sdk_retry", "market_data", "stock_order",
        "streaming",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 3C configuration keys are invalid")
    if raw["sdk_version"] != "2.0.17" or raw["region_id"] != "us":
        raise ValueError("unsupported Webull SDK version or region")
    if raw["webull_version"] != "3C.2.0":
        raise ValueError("unsupported Webull adapter configuration version")
    if raw["api_endpoint"] != API_SANDBOX_HOST:
        raise ValueError("only the Webull API sandbox host is allowed")
    if raw["events_endpoint"] != EVENTS_SANDBOX_HOST:
        raise ValueError("only the Webull events sandbox host is allowed")
    if raw["automatic_sdk_retry"] is not False:
        raise ValueError("automatic Webull SDK retry must remain disabled")
    credentials = raw["credential_environment"]
    if not isinstance(credentials, dict) or credentials != {
        "app_key": "WEBULL_APP_KEY", "app_secret": "WEBULL_APP_SECRET",
        "account_id": "WEBULL_ACCOUNT_ID",
    }:
        raise ValueError("Webull credential environment names are fixed")
    stock_order = raw["stock_order"]
    if stock_order != {"order_type": "MARKET", "time_in_force": "DAY"}:
        raise ValueError("unsupported Phase 3C stock-order policy")
    market_data = raw["market_data"]
    if not isinstance(market_data, dict) or set(market_data) != {
        "category", "trading_sessions", "real_time_required", "extended_hours",
        "max_completed_bar_lateness_seconds",
    }:
        raise ValueError("invalid Webull shadow market-data configuration")
    if (
        market_data["category"] != "US_STOCK"
        or market_data["trading_sessions"] != "RTH"
        or market_data["real_time_required"] is not False
        or market_data["extended_hours"] is not False
    ):
        raise ValueError("Webull shadow data must remain completed US-stock RTH only")
    lateness = market_data["max_completed_bar_lateness_seconds"]
    if isinstance(lateness, bool) or not isinstance(lateness, int) or lateness < 0:
        raise ValueError("invalid Webull completed-bar lateness")
    streaming = raw["streaming"]
    if not isinstance(streaming, dict) or set(streaming) != {
        "socket_enabled", "subscription_type", "trading_session", "stale_seconds",
        "reconciliation_interval_seconds", "reconnect_delays_seconds",
        "rest_reconciliation_required",
    }:
        raise ValueError("invalid Webull streaming configuration")
    if (
        streaming["socket_enabled"] is not False
        or streaming["subscription_type"] != "snapshot"
        or streaming["trading_session"] != "RTH"
        or streaming["rest_reconciliation_required"] is not True
        or streaming["reconnect_delays_seconds"] != [1, 2, 4]
    ):
        raise ValueError("Webull streaming must remain read-only and fail-closed")
    for key in ("stale_seconds", "reconciliation_interval_seconds"):
        if (
            isinstance(streaming[key], bool)
            or not isinstance(streaming[key], int)
            or streaming[key] <= 0
        ):
            raise ValueError("Webull streaming thresholds must be positive integers")
    for key in ("connect_timeout_seconds", "request_timeout_seconds"):
        if isinstance(raw[key], bool) or not isinstance(raw[key], int) or raw[key] <= 0:
            raise ValueError("Webull timeouts must be positive integers")
    return WebullConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
