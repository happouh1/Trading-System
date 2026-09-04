"""Strict Phase 7E configuration for hypothetical range entries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class RangeEntryConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RangeEntryConfig:
    values: Mapping[str, object]
    config_hash: str
    slippage_bps: Decimal
    slippage_atr20_fraction: Decimal
    maximum_adverse_gap_adr20: Decimal


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise RangeEntryConfigError(f"{name} must be numeric")
    try:
        result = Decimal(str(value))
    except ArithmeticError as exc:
        raise RangeEntryConfigError(f"{name} must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise RangeEntryConfigError(f"{name} must be finite and nonnegative")
    return result


def load_range_entry_config(path: str | Path) -> RangeEntryConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "entry_version", "entry", "provenance", "authority"
    }:
        raise RangeEntryConfigError("range entry top-level keys are invalid")
    if raw["entry_version"] != "7E.1.0":
        raise RangeEntryConfigError("entry_version must be 7E.1.0")
    entry = raw["entry"]
    provenance = raw["provenance"]
    authority = raw["authority"]
    expected_entry_keys = {
        "timing", "slippage_bps", "slippage_atr20_fraction",
        "maximum_adverse_gap_adr20", "require_completed_historical_candle",
        "require_context_known_by_evidence", "omit_when_next_candle_unavailable",
    }
    if not isinstance(entry, dict) or set(entry) != expected_entry_keys:
        raise RangeEntryConfigError("entry policy keys are invalid")
    if (
        entry["timing"] != "NEXT_ELIGIBLE_OPEN"
        or entry["require_completed_historical_candle"] is not True
        or entry["require_context_known_by_evidence"] is not True
        or entry["omit_when_next_candle_unavailable"] is not True
    ):
        raise RangeEntryConfigError("Phase 7E causal entry policy is invalid")
    if provenance != {
        "assumptions_inherited_from": "PHASE_1_EXECUTION_SIM",
        "currency_fees_included": False,
        "spread_quotes_included": False,
        "borrow_costs_included": False,
    }:
        raise RangeEntryConfigError("Phase 7E provenance disclosure is invalid")
    if authority != {
        "research_only": True,
        "hypothetical_entries_only": True,
        "exit_rule_enabled": False,
        "efficacy_claims_enabled": False,
        "scoring_enabled": False,
        "alerts_enabled": False,
        "options_routing_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
    }:
        raise RangeEntryConfigError("Phase 7E authority must remain research-only")
    frozen = MappingProxyType(
        {
            key: MappingProxyType(value) if isinstance(value, dict) else value
            for key, value in raw.items()
        }
    )
    return RangeEntryConfig(
        frozen,
        canonical_hash(raw),
        _decimal(entry["slippage_bps"], "slippage_bps"),
        _decimal(entry["slippage_atr20_fraction"], "slippage_atr20_fraction"),
        _decimal(entry["maximum_adverse_gap_adr20"], "maximum_adverse_gap_adr20"),
    )
