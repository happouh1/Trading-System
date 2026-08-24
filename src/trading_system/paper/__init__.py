"""Provider-neutral Phase 3B paper readiness."""

from trading_system.paper.adapters import InternalSimulatorAdapter, RejectingAdapter
from trading_system.paper.bridge import stage_shadow_decision
from trading_system.paper.config import PaperConfig, load_paper_config
from trading_system.paper.contracts import (
    AdapterResult,
    CompletedBarEnvelope,
    IntentStatus,
    OrderIntent,
    PaperMode,
    PaperSession,
    ReconciliationResult,
    RuntimeState,
)
from trading_system.paper.registry import PaperRegistry
from trading_system.paper.runtime import PaperRuntime

__all__ = [
    "AdapterResult", "CompletedBarEnvelope", "IntentStatus", "InternalSimulatorAdapter",
    "OrderIntent",
    "PaperConfig", "PaperMode", "PaperRegistry", "PaperRuntime", "PaperSession",
    "ReconciliationResult", "RejectingAdapter", "RuntimeState", "load_paper_config",
    "stage_shadow_decision",
]
