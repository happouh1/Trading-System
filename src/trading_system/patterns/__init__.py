"""Isolated, versioned causal pattern state machines."""

from trading_system.patterns.bases import BaseBar, BaseCandidate, BaseDetector
from trading_system.patterns.breaks import BreakPatternMachine, PatternBar
from trading_system.patterns.range_config import (
    RangeReclaimConfig,
    RangeReclaimConfigError,
    load_range_reclaim_config,
)
from trading_system.patterns.range_experiment import (
    RangeEvidenceGate,
    RangeExperimentAssignment,
    RangeExperimentMaterialization,
    RangeExperimentPlan,
    materialize_range_experiment,
    preregister_range_experiment,
)
from trading_system.patterns.range_experiment_config import (
    RangeExperimentConfig,
    RangeExperimentConfigError,
    load_range_experiment_config,
)
from trading_system.patterns.range_experiment_registry import RangeExperimentRegistry
from trading_system.patterns.range_reclaim import (
    BoundaryEpisode,
    RangeBoundary,
    RangeBox,
    RangeBoxDetector,
    VolumePointOfControl,
    assign_parent_box,
)
from trading_system.patterns.range_registry import RangeResearchRegistry
from trading_system.patterns.range_research import (
    RangeBoxOutcome,
    RangeResearchReplay,
    RangeResearchResult,
    RangeTerminalLocation,
    label_range_box,
)
from trading_system.patterns.range_research_config import (
    RangeResearchConfig,
    RangeResearchConfigError,
    load_range_research_config,
)
from trading_system.patterns.reclaims import ReclaimPatternMachine
from trading_system.patterns.sweeps import SweepPatternMachine

__all__ = [
    "BaseBar",
    "BaseCandidate",
    "BaseDetector",
    "BoundaryEpisode",
    "BreakPatternMachine",
    "PatternBar",
    "RangeBoundary",
    "RangeBox",
    "RangeBoxDetector",
    "RangeBoxOutcome",
    "RangeEvidenceGate",
    "RangeExperimentAssignment",
    "RangeExperimentConfig",
    "RangeExperimentConfigError",
    "RangeExperimentMaterialization",
    "RangeExperimentPlan",
    "RangeExperimentRegistry",
    "RangeReclaimConfig",
    "RangeReclaimConfigError",
    "RangeResearchConfig",
    "RangeResearchConfigError",
    "RangeResearchRegistry",
    "RangeResearchReplay",
    "RangeResearchResult",
    "RangeTerminalLocation",
    "ReclaimPatternMachine",
    "SweepPatternMachine",
    "VolumePointOfControl",
    "assign_parent_box",
    "label_range_box",
    "load_range_experiment_config",
    "load_range_reclaim_config",
    "load_range_research_config",
    "materialize_range_experiment",
    "preregister_range_experiment",
]
