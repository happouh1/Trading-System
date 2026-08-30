"""Strict, research-only Phase 4E capital-feasibility configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class OptionsCapitalConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OptionsCapitalConfig:
    values: Mapping[str, object]
    config_hash: str


def load_options_capital_config(path: str | Path) -> OptionsCapitalConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"capital_version", "authority", "ledger"}:
        raise OptionsCapitalConfigError("capital config top-level keys are invalid")
    if raw["capital_version"] != "4E.1.0":
        raise OptionsCapitalConfigError("capital_version must be 4E.1.0")
    if raw["authority"] != {
        "research_only": True,
        "automatic_allocation_enabled": False,
        "quantity_resizing_enabled": False,
        "options_execution_enabled": False,
        "portfolio_performance_claims_enabled": False,
    }:
        raise OptionsCapitalConfigError("Phase 4E authority must remain research-only")
    if raw["ledger"] != {
        "same_timestamp_policy": "ENTRY_BATCH_BEFORE_EXIT",
        "insufficient_batch_policy": "REJECT_ENTIRE_ENTRY_BATCH",
        "excluded_case_policy": "RECORD_ONLY",
        "intermediate_valuation": "UNAVAILABLE",
    }:
        raise OptionsCapitalConfigError("Phase 4E conservative ledger policy is locked")
    return OptionsCapitalConfig(MappingProxyType(dict(raw)), canonical_hash(raw))
