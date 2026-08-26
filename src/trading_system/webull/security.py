"""Credential loading and recursive Webull secret redaction."""

from __future__ import annotations

import os
from collections.abc import Mapping

from trading_system.webull.contracts import WebullCredentials

_SENSITIVE = {"authorization", "x-app-secret", "app_secret", "token", "access_token",
              "refresh_token", "signature", "x-signature", "account_id", "accountid",
              "account_number", "accountnumber", "user_id", "userid"}


def load_credentials(environment: Mapping[str, str] | None = None) -> WebullCredentials:
    source = os.environ if environment is None else environment
    return WebullCredentials(
        source.get("WEBULL_APP_KEY", "").strip(),
        source.get("WEBULL_APP_SECRET", "").strip(),
        source.get("WEBULL_ACCOUNT_ID", "").strip(),
    )


def submission_enabled(
    environment_name: str,
    environment: Mapping[str, str] | None = None,
) -> bool:
    if environment_name != "WEBULL_SANDBOX_SUBMISSION_ENABLED":
        raise ValueError("Webull submission environment flag name is invalid")
    source = os.environ if environment is None else environment
    return source.get(environment_name, "") == "true"


def redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE else redact(item)
                for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(redact(item) for item in value)
    return value
