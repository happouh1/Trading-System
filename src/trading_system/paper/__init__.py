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
from trading_system.paper.operator_control import (
    OperatorHealth,
    PaperOperatorConfig,
    PaperOperatorJob,
    PaperOperatorSnapshot,
    build_operator_jobs,
    load_paper_operator_config,
)
from trading_system.paper.operator_control_registry import PaperOperatorRegistry
from trading_system.paper.registry import PaperRegistry
from trading_system.paper.runtime import PaperRuntime

__all__ = [
    "AdapterResult",
    "CompletedBarEnvelope",
    "IntentStatus",
    "InternalSimulatorAdapter",
    "OperatorHealth",
    "OrderIntent",
    "PaperConfig",
    "PaperMode",
    "PaperOperatorConfig",
    "PaperOperatorJob",
    "PaperOperatorRegistry",
    "PaperOperatorSnapshot",
    "PaperRegistry",
    "PaperRuntime",
    "PaperSession",
    "ReconciliationResult",
    "RejectingAdapter",
    "RuntimeState",
    "build_operator_jobs",
    "load_paper_config",
    "load_paper_operator_config",
    "stage_shadow_decision",
]
