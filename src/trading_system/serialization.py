"""Canonical, locale-independent JSON serialization."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


def canonical_value(value: object) -> Any:
    """Convert supported values to a canonical JSON-compatible representation."""
    if is_dataclass(value) and not isinstance(value, type):
        result = {field.name: canonical_value(getattr(value, field.name)) for field in fields(value)}
        result["__type__"] = type(value).__name__
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal is not canonicalizable")
        return {"__decimal__": format(value, "f")}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetimes must be timezone-aware")
        text = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
        return {"__datetime__": text.replace("+00:00", "Z")}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical mapping keys must be strings")
        return {key: canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not canonicalizable")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(canonical_value(value), ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def canonical_hash(value: object) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def deterministic_id(namespace: str, value: object) -> str:
    if not namespace or not namespace.replace("_", "").isalnum():
        raise ValueError("namespace must contain only letters, numbers, and underscores")
    digest = canonical_hash({"namespace": namespace, "value": value})[7:]
    return f"{namespace}_{digest[:32]}"

