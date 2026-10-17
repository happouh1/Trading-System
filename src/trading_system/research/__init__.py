"""Phase 2A empirical research isolated from Phase 1 decision authority."""

from trading_system.research.contracts import (
    ExperimentSpec,
    ExperimentStatus,
    HumanReview,
    ResearchRow,
    ReviewVerdict,
    UniverseMembership,
    WalkForwardFold,
    WalkForwardSpec,
    eligible_truth_reviews,
)
from trading_system.research.folds import build_walk_forward_folds, eligible_labeled_rows
from trading_system.research.trend_stage_a import (
    StageAAssessment,
    StageAConfig,
    StageAConfigError,
    StageAObservation,
    StageAState,
    StageATimeBucket,
    StageAVolumeBand,
    assess_stage_a,
    load_stage_a_config,
)
from trading_system.research.universe import PointInTimeUniverse

__all__ = [
    "ExperimentSpec",
    "ExperimentStatus",
    "HumanReview",
    "PointInTimeUniverse",
    "ResearchRow",
    "ReviewVerdict",
    "StageAAssessment",
    "StageAConfig",
    "StageAConfigError",
    "StageAObservation",
    "StageAState",
    "StageATimeBucket",
    "StageAVolumeBand",
    "UniverseMembership",
    "WalkForwardFold",
    "WalkForwardSpec",
    "assess_stage_a",
    "build_walk_forward_folds",
    "eligible_labeled_rows",
    "eligible_truth_reviews",
    "load_stage_a_config",
]
