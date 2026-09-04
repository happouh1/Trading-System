"""Strict Phase 7F fixed-horizon outcome configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.domain import Timeframe
from trading_system.serialization import canonical_hash


class RangeOutcomeConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeOutcomeConfig:
    values: Mapping[str, object]
    config_hash: str

    def horizons(self, timeframe: Timeframe) -> tuple[int, ...]:
        horizons = self.values["horizons"]
        assert isinstance(horizons, Mapping)
        value = horizons.get(timeframe.value, ())
        if not isinstance(value, tuple):
            raise RangeOutcomeConfigError("validated horizons must be tuples")
        return value


def load_range_outcome_config(path: str | Path) -> RangeOutcomeConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "outcome_version", "horizons", "exit", "authority"
    }:
        raise RangeOutcomeConfigError("range outcome top-level keys are invalid")
    if raw["outcome_version"] != "7F.1.0":
        raise RangeOutcomeConfigError("outcome_version must be 7F.1.0")
    expected_horizons = {
        "1h": [1, 3, 6, 12, 24, 48],
        "4h": [1, 3, 6, 12, 24],
        "1d": [1, 3, 5, 10, 20, 60],
    }
    if raw["horizons"] != expected_horizons:
        raise RangeOutcomeConfigError("Phase 7F horizons must match Phase 7B")
    if raw["exit"] != {
        "timing": "CONFIGURED_HORIZON_CLOSE",
        "include_entry_candle_as_bar_one": True,
        "retain_every_mature_horizon": True,
        "exit_slippage": "REUSE_ENTRY_CAUSAL_SLIPPAGE",
        "fees_included": False,
        "borrow_costs_included": False,
    }:
        raise RangeOutcomeConfigError("Phase 7F exit policy is invalid")
    if raw["authority"] != {
        "research_outcomes_only": True,
        "efficacy_claims_enabled": False,
        "parameter_selection_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeOutcomeConfigError("Phase 7F authority must remain research-only")
    frozen = dict(raw)
    frozen["horizons"] = MappingProxyType(
        {key: tuple(value) for key, value in expected_horizons.items()}
    )
    exit_policy = raw["exit"]
    authority = raw["authority"]
    assert isinstance(exit_policy, dict) and isinstance(authority, dict)
    frozen["exit"] = MappingProxyType(dict(exit_policy))
    frozen["authority"] = MappingProxyType(dict(authority))
    return RangeOutcomeConfig(MappingProxyType(frozen), canonical_hash(raw))
