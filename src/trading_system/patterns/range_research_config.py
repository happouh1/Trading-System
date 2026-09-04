"""Strict Phase 7B configuration for offline range-box research replay."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.domain import Timeframe
from trading_system.serialization import canonical_hash


class RangeResearchConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeResearchConfig:
    values: Mapping[str, object]
    config_hash: str

    def horizons(self, timeframe: Timeframe) -> tuple[int, ...]:
        section = self.values.get("horizons")
        if not isinstance(section, Mapping):
            raise RangeResearchConfigError("horizons must be an object")
        raw = section.get(timeframe.value)
        if raw is None:
            return ()
        if not isinstance(raw, tuple):
            raise RangeResearchConfigError("validated horizon values must be tuples")
        return raw


def load_range_research_config(path: str | Path) -> RangeResearchConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "research_version",
        "label_version",
        "horizons",
        "terminal_location",
        "authority",
    }:
        raise RangeResearchConfigError("range research config top-level keys are invalid")
    if raw["research_version"] != "7B.1.0" or raw["label_version"] != "1.0.0":
        raise RangeResearchConfigError("Phase 7B versions are fixed")
    horizons = raw["horizons"]
    expected = {
        Timeframe.HOUR_1.value: [1, 3, 6, 12, 24, 48],
        Timeframe.HOUR_4.value: [1, 3, 6, 12, 24],
        Timeframe.DAY_1.value: [1, 3, 5, 10, 20, 60],
    }
    if horizons != expected:
        raise RangeResearchConfigError("Phase 7B horizons must match the approved specification")
    if raw["terminal_location"] != {
        "above_when_close_strictly_above_upper": True,
        "below_when_close_strictly_below_lower": True,
        "boundary_close_is_inside": True,
    }:
        raise RangeResearchConfigError("terminal-location policy is invalid")
    if raw["authority"] != {
        "research_only": True,
        "descriptive_labels_only": True,
        "replay_decisions_enabled": False,
        "scoring_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeResearchConfigError("Phase 7B authority must remain research-only")
    frozen = dict(raw)
    frozen["horizons"] = MappingProxyType(
        {key: tuple(value) for key, value in expected.items()}
    )
    terminal_location = raw["terminal_location"]
    authority = raw["authority"]
    assert isinstance(terminal_location, dict) and isinstance(authority, dict)
    frozen["terminal_location"] = MappingProxyType(dict(terminal_location))
    frozen["authority"] = MappingProxyType(dict(authority))
    return RangeResearchConfig(MappingProxyType(frozen), canonical_hash(raw))
