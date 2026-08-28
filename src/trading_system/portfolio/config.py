"""Strict versioned Phase 4A portfolio-research configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.portfolio.contracts import StrategyClass
from trading_system.serialization import canonical_hash


class PortfolioConfigError(ValueError):
    pass


def _decimal(value: object, path: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PortfolioConfigError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise PortfolioConfigError(f"{path} must be numeric") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        qualifier = "positive" if positive else "nonnegative"
        raise PortfolioConfigError(f"{path} must be finite and {qualifier}")
    return result


@dataclass(frozen=True, slots=True)
class PortfolioConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise PortfolioConfigError(f"{name} must be an object")
        return value

    def decimal(self, section: str, key: str) -> Decimal:
        return _decimal(self.section(section).get(key), f"{section}.{key}")

    def integer(self, section: str, key: str) -> int:
        value = self.section(section).get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise PortfolioConfigError(f"{section}.{key} must be an integer")
        return value


def load_portfolio_config(path: str | Path) -> PortfolioConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PortfolioConfigError("portfolio config must be an object")
    if set(raw) != {
        "portfolio_version",
        "classification",
        "liquidity",
        "exposure",
        "strategy_risk_budget_pct",
        "authority",
    }:
        raise PortfolioConfigError("portfolio config top-level keys are invalid")
    if raw["portfolio_version"] != "4A.1.0":
        raise PortfolioConfigError("portfolio_version must be 4A.1.0")

    classification = raw["classification"]
    if not isinstance(classification, dict) or set(classification) != {
        "intraday_max_sessions",
        "swing_max_sessions",
        "position_max_sessions",
    }:
        raise PortfolioConfigError("classification configuration is invalid")
    boundaries = tuple(classification[key] for key in (
        "intraday_max_sessions", "swing_max_sessions", "position_max_sessions"
    ))
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in boundaries):
        raise PortfolioConfigError("classification boundaries must be integers")
    if not (0 < boundaries[0] < boundaries[1] < boundaries[2]):
        raise PortfolioConfigError("classification boundaries must increase")

    liquidity = raw["liquidity"]
    if not isinstance(liquidity, dict) or set(liquidity) != {
        "minimum_price",
        "minimum_average_daily_dollar_volume",
        "maximum_volume_participation",
    }:
        raise PortfolioConfigError("liquidity configuration is invalid")
    _decimal(liquidity["minimum_price"], "liquidity.minimum_price", positive=True)
    _decimal(
        liquidity["minimum_average_daily_dollar_volume"],
        "liquidity.minimum_average_daily_dollar_volume",
        positive=True,
    )
    maximum_participation = _decimal(
        liquidity["maximum_volume_participation"],
        "liquidity.maximum_volume_participation",
        positive=True,
    )
    if maximum_participation > 1:
        raise PortfolioConfigError("maximum volume participation cannot exceed one")

    exposure = raw["exposure"]
    if not isinstance(exposure, dict) or set(exposure) != {
        "maximum_positions",
        "maximum_gross_exposure_pct",
        "maximum_absolute_net_exposure_pct",
        "maximum_position_exposure_pct",
        "maximum_sector_exposure_pct",
        "duplicate_symbol_policy",
    }:
        raise PortfolioConfigError("exposure configuration is invalid")
    maximum_positions = exposure["maximum_positions"]
    if not isinstance(maximum_positions, int) or isinstance(maximum_positions, bool):
        raise PortfolioConfigError("maximum_positions must be an integer")
    if maximum_positions <= 0:
        raise PortfolioConfigError("maximum_positions must be positive")
    for key in (
        "maximum_gross_exposure_pct",
        "maximum_absolute_net_exposure_pct",
        "maximum_position_exposure_pct",
        "maximum_sector_exposure_pct",
    ):
        value = _decimal(exposure[key], f"exposure.{key}", positive=True)
        if value > 1:
            raise PortfolioConfigError(f"exposure.{key} cannot exceed one")
    if exposure["duplicate_symbol_policy"] != "REJECT":
        raise PortfolioConfigError("duplicate_symbol_policy must be REJECT")

    budgets = raw["strategy_risk_budget_pct"]
    expected_strategies = {item.value for item in StrategyClass}
    if not isinstance(budgets, dict) or set(budgets) != expected_strategies:
        raise PortfolioConfigError("strategy risk budgets are invalid")
    for key, value in budgets.items():
        budget = _decimal(value, f"strategy_risk_budget_pct.{key}")
        if budget > 1:
            raise PortfolioConfigError(f"strategy_risk_budget_pct.{key} cannot exceed one")
    if _decimal(budgets[StrategyClass.LONG_TERM_RESEARCH.value], "long-term budget") != 0:
        raise PortfolioConfigError("LONG_TERM_RESEARCH budget must remain zero in Phase 4A")

    authority = raw["authority"]
    required_authority = {
        "research_only": True,
        "broker_writes_enabled": False,
        "options_enabled": False,
        "long_term_requires_fundamentals": True,
    }
    if authority != required_authority:
        raise PortfolioConfigError("Phase 4A authority must remain research-only")

    return PortfolioConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
