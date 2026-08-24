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
        "request_timeout_seconds", "automatic_sdk_retry", "stock_order",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("Phase 3C configuration keys are invalid")
    if raw["sdk_version"] != "2.0.17" or raw["region_id"] != "us":
        raise ValueError("unsupported Webull SDK version or region")
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
    for key in ("connect_timeout_seconds", "request_timeout_seconds"):
        if isinstance(raw[key], bool) or not isinstance(raw[key], int) or raw[key] <= 0:
            raise ValueError("Webull timeouts must be positive integers")
    return WebullConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
