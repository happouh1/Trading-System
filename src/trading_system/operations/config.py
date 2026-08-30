"""Strict Phase 5A inspection-only operations configuration."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from trading_system.serialization import canonical_hash


class OperationsConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OperationsConfig:
    components: Mapping[str, tuple[str, ...]]
    config_hash: str


_COMPONENTS = (
    "CORE_RESEARCH",
    "RESEARCH_EVALUATION",
    "MODELING",
    "PAPER",
    "WEBULL_SANDBOX",
    "PORTFOLIO",
    "OPTIONS",
)
_TABLES = {
    "CORE_RESEARCH": ["runs", "candles", "feature_snapshots", "decisions"],
    "RESEARCH_EVALUATION": ["experiments", "experiment_reports"],
    "MODELING": ["model_experiments", "model_reports"],
    "PAPER": ["paper_sessions", "paper_reconciliations"],
    "WEBULL_SANDBOX": ["webull_connection_verifications", "webull_reconciliations"],
    "PORTFOLIO": ["portfolio_states", "portfolio_assessments"],
    "OPTIONS": [
        "option_validation_results",
        "option_experiment_transitions",
        "option_capital_reports",
    ],
}


def load_operations_config(path: str | Path) -> OperationsConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "operations_version",
        "authority",
        "components",
        "policy",
    }:
        raise OperationsConfigError("operations config top-level keys are invalid")
    if raw["operations_version"] != "5A.1.0":
        raise OperationsConfigError("operations_version must be 5A.1.0")
    if raw["authority"] != {
        "inspection_only": True,
        "workflow_execution_enabled": False,
        "broker_writes_enabled": False,
        "live_trading_enabled": False,
        "automatic_promotion_enabled": False,
    }:
        raise OperationsConfigError("Phase 5A authority must remain inspection-only")
    if raw["policy"] != {
        "missing_database": "NOT_READY",
        "missing_table": "NOT_READY",
        "empty_required_table": "NOT_READY",
        "all_components_required": True,
    }:
        raise OperationsConfigError("Phase 5A fail-closed policy is locked")
    components = raw["components"]
    if not isinstance(components, dict) or tuple(components) != _COMPONENTS:
        raise OperationsConfigError("Phase 5A component order and names are locked")
    if components != _TABLES:
        raise OperationsConfigError("Phase 5A evidence table requirements are locked")
    normalized: dict[str, tuple[str, ...]] = {}
    for name in _COMPONENTS:
        tables = components[name]
        if (
            not isinstance(tables, list)
            or not tables
            or not all(isinstance(item, str) and item for item in tables)
            or len(set(tables)) != len(tables)
        ):
            raise OperationsConfigError(f"{name} tables must be unique nonempty strings")
        normalized[name] = tuple(tables)
    return OperationsConfig(MappingProxyType(normalized), canonical_hash(raw))
