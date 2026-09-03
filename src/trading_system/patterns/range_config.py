"""Strict research-only configuration for Phase 7A range boxes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class RangeReclaimConfigError(ValueError):
    """Raised when Phase 7A configuration is incomplete or unsafe."""


def _integer(value: object, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RangeReclaimConfigError(f"{path} must be an integer >= {minimum}")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RangeReclaimConfigError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise RangeReclaimConfigError(f"{path} must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise RangeReclaimConfigError(f"{path} must be finite and nonnegative")
    return result


@dataclass(frozen=True, slots=True)
class RangeReclaimConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise RangeReclaimConfigError(f"{name} must be an object")
        return value

    @property
    def min_bars(self) -> int:
        return _integer(self.section("box").get("min_bars"), "box.min_bars", minimum=2)

    @property
    def max_bars(self) -> int:
        return _integer(self.section("box").get("max_bars"), "box.max_bars", minimum=2)

    @property
    def contact_tolerance_adr(self) -> Decimal:
        return _decimal(
            self.section("box").get("contact_tolerance_adr"),
            "box.contact_tolerance_adr",
        )

    @property
    def minimum_lower_episodes(self) -> int:
        return _integer(
            self.section("box").get("minimum_lower_episodes"),
            "box.minimum_lower_episodes",
            minimum=1,
        )

    @property
    def minimum_upper_episodes(self) -> int:
        return _integer(
            self.section("box").get("minimum_upper_episodes"),
            "box.minimum_upper_episodes",
            minimum=1,
        )


def load_range_reclaim_config(path: str | Path) -> RangeReclaimConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "strategy_version",
        "strategy_family",
        "box",
        "volume_profile",
        "nesting",
        "authority",
    }:
        raise RangeReclaimConfigError("range-reclaim config top-level keys are invalid")
    if raw["strategy_version"] != "7A.1.0":
        raise RangeReclaimConfigError("strategy_version must be 7A.1.0")
    if raw["strategy_family"] != "RANGE_RECLAIM_CONTINUATION_V1":
        raise RangeReclaimConfigError("strategy_family is invalid")
    box = raw["box"]
    if not isinstance(box, dict) or set(box) != {
        "min_bars",
        "max_bars",
        "contact_tolerance_adr",
        "minimum_lower_episodes",
        "minimum_upper_episodes",
        "reject_dual_boundary_bars",
    }:
        raise RangeReclaimConfigError("box configuration is invalid")
    config = RangeReclaimConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
    if config.max_bars < config.min_bars:
        raise RangeReclaimConfigError("box.max_bars must be >= box.min_bars")
    if config.contact_tolerance_adr > Decimal("0.50"):
        raise RangeReclaimConfigError("box.contact_tolerance_adr must be <= 0.50")
    if box["reject_dual_boundary_bars"] is not True:
        raise RangeReclaimConfigError("Phase 7A must reject dual-boundary bars")
    if raw["volume_profile"] != {
        "require_observed_poc": False,
        "infer_poc_from_ohlcv": False,
    }:
        raise RangeReclaimConfigError("Phase 7A may not infer volume POC from OHLCV")
    if raw["nesting"] != {
        "enabled": True,
        "require_parent_known_before_child": True,
    }:
        raise RangeReclaimConfigError("Phase 7A nesting safety policy is invalid")
    if raw["authority"] != {
        "research_only": True,
        "replay_integration_enabled": False,
        "scoring_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeReclaimConfigError("Phase 7A authority must remain research-only")
    return config
