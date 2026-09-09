"""Provider-neutral Phase 3B paper readiness."""

from trading_system.paper.adapters import InternalSimulatorAdapter, RejectingAdapter
from trading_system.paper.bridge import stage_shadow_decision
from trading_system.paper.burn_in import (
    BurnInState,
    PaperBurnInAssessment,
    PaperBurnInConfig,
    PaperBurnInProtocol,
    build_burn_in_protocol,
    evaluate_burn_in,
    load_paper_burn_in_config,
)
from trading_system.paper.burn_in_registry import PaperBurnInRegistry
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
    "BurnInState",
    "CompletedBarEnvelope",
    "IntentStatus",
    "InternalSimulatorAdapter",
    "OperatorHealth",
    "OrderIntent",
    "PaperBurnInAssessment",
    "PaperBurnInConfig",
    "PaperBurnInProtocol",
    "PaperBurnInRegistry",
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
    "build_burn_in_protocol",
    "build_operator_jobs",
    "evaluate_burn_in",
    "load_paper_burn_in_config",
    "load_paper_config",
    "load_paper_operator_config",
    "stage_shadow_decision",
]
