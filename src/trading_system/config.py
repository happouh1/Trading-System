"""Dependency-free validation for the versioned JSON-compatible YAML config."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from trading_system.serialization import canonical_hash
from trading_system.versioning import SPEC_VERSION, SemanticVersion

_TOP_LEVEL = {
    "spec_version", "calendar", "session", "adjustment", "timeframes", "signal_timeframes",
    "features", "structure", "trend", "base", "break", "acceptance", "sweep", "trap",
    "risk", "decision", "execution", "determinism",
}
_REQUIRED_TOP_LEVEL = _TOP_LEVEL - {"trend", "sweep", "trap"}
_TIMEFRAMES = {"1h", "4h", "1d", "1w"}


class ConfigError(ValueError):
    """Configuration failed structural or semantic validation."""


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ConfigError(f"{path} must be an object with string keys")
    return value


def _number(value: object, path: str, low: float = 0.0, high: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be numeric")
    if value < low or (high is not None and value > high):
        raise ConfigError(f"{path} must be in [{low}, {high if high is not None else 'infinity'}]")


def _keys(section: dict[str, Any], path: str, expected: set[str]) -> None:
    missing, extra = expected - section.keys(), section.keys() - expected
    if missing or extra:
        raise ConfigError(f"{path} keys invalid; missing={sorted(missing)}, extra={sorted(extra)}")


@dataclass(frozen=True, slots=True)
class ThresholdConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values[name]
        if not isinstance(value, Mapping):
            raise ConfigError(f"{name} is not an object")
        return value


def validate_config(raw: object) -> ThresholdConfig:
    root = _object(raw, "config")
    missing = _REQUIRED_TOP_LEVEL - root.keys()
    extra = root.keys() - _TOP_LEVEL
    if missing or extra:
        raise ConfigError(
            f"config keys invalid; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    phase1d_sections = {"trend", "sweep", "trap"}
    present_phase1d = phase1d_sections & root.keys()
    if present_phase1d and present_phase1d != phase1d_sections:
        raise ConfigError("trend, sweep, and trap sections must be supplied together")
    if root["spec_version"] != SPEC_VERSION:
        raise ConfigError(f"spec_version must be {SPEC_VERSION}")
    SemanticVersion.parse(str(root["spec_version"]))
    if root["calendar"] != "XNYS" or root["session"] != "regular":
        raise ConfigError("Phase 0 baseline requires XNYS regular session")
    if root["adjustment"] != "split_adjusted":
        raise ConfigError("Phase 0 baseline requires split_adjusted")
    timeframes = root["timeframes"]
    signals = root["signal_timeframes"]
    if not isinstance(timeframes, list) or set(timeframes) != _TIMEFRAMES:
        raise ConfigError("timeframes must contain 1h, 4h, 1d, and 1w exactly once")
    if len(timeframes) != len(set(timeframes)):
        raise ConfigError("timeframes must be unique")
    if not isinstance(signals, list) or not signals or not set(signals) <= {"1h", "4h"}:
        raise ConfigError("signal_timeframes must be a nonempty subset of 1h and 4h")

    expected = {
        "features": {"atr_period", "adr_period", "rvol_period", "pivot_left", "pivot_right"},
        "structure": {"equality_tolerance_adr"},
        "trend": {"ema_slope_lookback_bars", "ema_slope_full_scale"},
        "base": {
            "min_bars",
            "max_bars",
            "max_width_adr",
            "max_net_drift_adr",
            "min_overlap",
            "max_atr_compression",
        },
        "break": {"buffer_adr", "min_clv_long", "max_clv_short", "min_body_fraction", "min_rvol"},
        "acceptance": {
            "window_bars",
            "required_closes",
            "hold_buffer_adr",
            "failure_buffer_adr",
            "min_score",
        },
        "sweep": {"min_wick_fraction", "full_quality_wick_fraction"},
        "trap": {
            "full_failure_distance_adr",
            "full_participation_rvol",
            "full_participation_excursion_adr",
            "full_follow_through_adr",
        },
        "risk": {
            "stop_buffer_adr",
            "min_stop_adr",
            "max_stop_adr",
            "min_runway_adr",
            "min_reward_risk",
            "max_hold_bars",
        },
        "decision": {"trade_confidence", "watch_confidence"},
        "execution": {"fill_model", "collision_policy", "slippage_bps", "slippage_atr_fraction"},
        "determinism": {"seed", "numeric_rounding", "price_precision"},
    }
    sections = {
        name: _object(root[name], name)
        for name in expected
        if name in root
    }
    for name, keys in expected.items():
        if name not in sections:
            continue
        _keys(sections[name], name, keys)

    for key in expected["features"]:
        _number(sections["features"][key], f"features.{key}", 1)
    for name in ("structure", "base", "break", "acceptance", "risk", "decision"):
        for key, value in sections[name].items():
            _number(value, f"{name}.{key}")
    for name in ("trend", "sweep", "trap"):
        for key, value in sections.get(name, {}).items():
            _number(value, f"{name}.{key}")
    if "trend" in sections and (
        isinstance(sections["trend"]["ema_slope_lookback_bars"], bool)
        or not isinstance(sections["trend"]["ema_slope_lookback_bars"], int)
    ):
        raise ConfigError("trend.ema_slope_lookback_bars must be an integer")
    for path in (("base", "min_overlap"), ("break", "min_clv_long"),
                 ("break", "max_clv_short"), ("break", "min_body_fraction")):
        _number(sections[path[0]][path[1]], ".".join(path), 0, 1)
    if sections["base"]["min_bars"] > sections["base"]["max_bars"]:
        raise ConfigError("base.min_bars cannot exceed base.max_bars")
    if sections["acceptance"]["required_closes"] > sections["acceptance"]["window_bars"]:
        raise ConfigError("acceptance.required_closes cannot exceed window_bars")
    if "sweep" in sections and (
        sections["sweep"]["min_wick_fraction"]
        >= sections["sweep"]["full_quality_wick_fraction"]
    ):
        raise ConfigError("sweep minimum wick must be below full-quality wick")
    if sections["risk"]["min_stop_adr"] > sections["risk"]["max_stop_adr"]:
        raise ConfigError("risk.min_stop_adr cannot exceed max_stop_adr")
    if sections["decision"]["watch_confidence"] > sections["decision"]["trade_confidence"]:
        raise ConfigError("watch_confidence cannot exceed trade_confidence")
    for key in ("trade_confidence", "watch_confidence"):
        _number(sections["decision"][key], f"decision.{key}", 0, 100)
    execution = sections["execution"]
    invalid_execution = (
        execution["fill_model"] != "next_bar_open"
        or execution["collision_policy"] != "adverse_first"
    )
    if invalid_execution:
        raise ConfigError("unsupported Phase 0 execution baseline")
    _number(execution["slippage_bps"], "execution.slippage_bps")
    _number(execution["slippage_atr_fraction"], "execution.slippage_atr_fraction")
    determinism = sections["determinism"]
    if determinism["numeric_rounding"] != "half_even":
        raise ConfigError("numeric_rounding must be half_even")
    _number(determinism["price_precision"], "determinism.price_precision", 0, 18)
    if isinstance(determinism["seed"], bool) or not isinstance(determinism["seed"], int):
        raise ConfigError("determinism.seed must be an integer")
    return ThresholdConfig(MappingProxyType(dict(root)), canonical_hash(root))


def load_config(path: str | Path) -> ThresholdConfig:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read JSON-compatible YAML config: {exc}") from exc
    return validate_config(raw)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m trading_system.config CONFIG", file=sys.stderr)
        return 2
    config = load_config(args[0])
    print(config.config_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
