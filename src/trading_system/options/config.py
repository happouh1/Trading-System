"""Strict versioned Phase 4B option-screening configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.options.contracts import OptionHorizon
from trading_system.serialization import canonical_hash


class OptionsConfigError(ValueError):
    pass


def _decimal(value: object, path: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise OptionsConfigError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise OptionsConfigError(f"{path} must be numeric") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise OptionsConfigError(f"{path} must be finite and nonnegative")
    return result


def _integer(value: object, path: str, *, positive: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise OptionsConfigError(f"{path} must be an integer")
    if value < 0 or (positive and value <= 0):
        raise OptionsConfigError(f"{path} must be nonnegative")
    return value


@dataclass(frozen=True, slots=True)
class OptionsConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise OptionsConfigError(f"{name} must be an object")
        return value

    def decimal(self, section: str, key: str) -> Decimal:
        return _decimal(self.section(section).get(key), f"{section}.{key}")

    def integer(self, section: str, key: str) -> int:
        return _integer(self.section(section).get(key), f"{section}.{key}")

    def horizon(self, horizon: OptionHorizon) -> Mapping[str, object]:
        value = self.section("horizons").get(horizon.value)
        if not isinstance(value, Mapping):
            raise OptionsConfigError(f"missing horizon {horizon.value}")
        return value

    def horizon_integer(self, horizon: OptionHorizon, key: str) -> int:
        return _integer(self.horizon(horizon).get(key), f"horizons.{horizon.value}.{key}")

    def horizon_decimal(self, horizon: OptionHorizon, key: str) -> Decimal:
        return _decimal(self.horizon(horizon).get(key), f"horizons.{horizon.value}.{key}")


def load_options_config(path: str | Path) -> OptionsConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "options_version", "product", "quote", "horizons", "authority"
    }:
        raise OptionsConfigError("options config top-level keys are invalid")
    if raw["options_version"] != "4B.1.0":
        raise OptionsConfigError("options_version must be 4B.1.0")
    if raw["product"] != {
        "classification": "EQUITY",
        "standard_contract_required": True,
        "required_multiplier": 100,
        "exercise_style": "AMERICAN",
        "settlement_type": "PHYSICAL",
    }:
        raise OptionsConfigError("Phase 4B supports standard US equity options only")
    quote = raw["quote"]
    if not isinstance(quote, dict) or set(quote) != {
        "maximum_age_seconds",
        "minimum_bid",
        "minimum_volume",
        "minimum_open_interest",
        "maximum_absolute_spread",
        "maximum_relative_spread",
        "require_implied_volatility",
        "require_delta",
    }:
        raise OptionsConfigError("quote configuration is invalid")
    _integer(quote["maximum_age_seconds"], "quote.maximum_age_seconds", positive=True)
    _integer(quote["minimum_volume"], "quote.minimum_volume")
    _integer(quote["minimum_open_interest"], "quote.minimum_open_interest")
    for key in ("minimum_bid", "maximum_absolute_spread", "maximum_relative_spread"):
        _decimal(quote[key], f"quote.{key}", positive=True)
    if quote["require_implied_volatility"] is not True or quote["require_delta"] is not True:
        raise OptionsConfigError("Phase 4B requires provider IV and delta")

    horizons = raw["horizons"]
    if not isinstance(horizons, dict) or set(horizons) != {item.value for item in OptionHorizon}:
        raise OptionsConfigError("horizon configuration is invalid")
    for name, value in horizons.items():
        if not isinstance(value, dict) or set(value) != {
            "minimum_dte", "target_dte", "maximum_dte",
            "minimum_absolute_delta", "target_absolute_delta", "maximum_absolute_delta"
        }:
            raise OptionsConfigError(f"horizon {name} configuration is invalid")
        dtes = tuple(
            _integer(value[key], f"horizons.{name}.{key}", positive=True)
            for key in ("minimum_dte", "target_dte", "maximum_dte")
        )
        deltas = tuple(
            _decimal(value[key], f"horizons.{name}.{key}", positive=True)
            for key in (
                "minimum_absolute_delta", "target_absolute_delta", "maximum_absolute_delta"
            )
        )
        if not (dtes[0] <= dtes[1] <= dtes[2]):
            raise OptionsConfigError(f"horizon {name} DTE values must increase")
        if not (Decimal(0) < deltas[0] <= deltas[1] <= deltas[2] <= Decimal(1)):
            raise OptionsConfigError(f"horizon {name} delta values must increase within (0,1]")

    if raw["authority"] != {
        "research_only": True,
        "long_premium_only": True,
        "broker_writes_enabled": False,
        "options_execution_enabled": False,
        "multi_leg_enabled": False,
        "provider_greeks_are_observations_only": True,
    }:
        raise OptionsConfigError("Phase 4B authority must remain research-only")
    return OptionsConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
