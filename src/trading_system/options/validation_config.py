"""Strict Phase 4C conservative option-validation configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class OptionsValidationConfigError(ValueError):
    pass


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise OptionsValidationConfigError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise OptionsValidationConfigError(f"{path} must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise OptionsValidationConfigError(f"{path} must be finite and nonnegative")
    return result


@dataclass(frozen=True, slots=True)
class OptionsValidationConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise OptionsValidationConfigError(f"{name} must be an object")
        return value

    def decimal(self, section: str, key: str) -> Decimal:
        return _decimal(self.section(section).get(key), f"{section}.{key}")

    def integer(self, section: str, key: str) -> int:
        value = self.section(section).get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise OptionsValidationConfigError(f"{section}.{key} must be a positive integer")
        return value


def load_options_validation_config(path: str | Path) -> OptionsValidationConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "validation_version",
        "fills",
        "data_quality",
        "authority",
    }:
        raise OptionsValidationConfigError("validation config top-level keys are invalid")
    if raw["validation_version"] != "4C.1.0":
        raise OptionsValidationConfigError("validation_version must be 4C.1.0")
    fills = raw["fills"]
    expected_fills = {
        "entry_side": "ASK",
        "exit_side": "BID",
        "slippage_per_share_per_side": fills.get("slippage_per_share_per_side")
        if isinstance(fills, dict)
        else None,
        "fee_per_contract_per_side": fills.get("fee_per_contract_per_side")
        if isinstance(fills, dict)
        else None,
    }
    if not isinstance(fills, dict) or set(fills) != set(expected_fills):
        raise OptionsValidationConfigError("fill configuration is invalid")
    if fills["entry_side"] != "ASK" or fills["exit_side"] != "BID":
        raise OptionsValidationConfigError("Phase 4C requires conservative ask-entry/bid-exit")
    _decimal(fills["slippage_per_share_per_side"], "fills.slippage_per_share_per_side")
    _decimal(fills["fee_per_contract_per_side"], "fills.fee_per_contract_per_side")
    data_quality = raw["data_quality"]
    if not isinstance(data_quality, dict) or set(data_quality) != {
        "maximum_quote_age_seconds",
        "require_post_signal_entry_quote",
        "require_post_entry_exit_quote",
        "disallow_expiration_day",
        "missing_or_stale_quote_policy",
    }:
        raise OptionsValidationConfigError("Phase 4C data-quality policy is locked")
    if (
        data_quality["require_post_signal_entry_quote"] is not True
        or data_quality["require_post_entry_exit_quote"] is not True
        or data_quality["disallow_expiration_day"] is not True
        or data_quality["missing_or_stale_quote_policy"] != "EXCLUDE"
    ):
        raise OptionsValidationConfigError("Phase 4C data-quality policy is locked")
    maximum_age = data_quality["maximum_quote_age_seconds"]
    if not isinstance(maximum_age, int) or isinstance(maximum_age, bool) or maximum_age <= 0:
        raise OptionsValidationConfigError("maximum quote age must be a positive integer")
    if raw["authority"] != {
        "research_only": True,
        "externally_supplied_exit_only": True,
        "broker_writes_enabled": False,
        "options_execution_enabled": False,
        "exercise_assignment_model_enabled": False,
        "theoretical_pricing_enabled": False,
    }:
        raise OptionsValidationConfigError("Phase 4C authority must remain research-only")
    return OptionsValidationConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
