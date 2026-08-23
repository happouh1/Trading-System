"""Restart-safe Phase 2B workflow over the append-only registry."""

from __future__ import annotations

from datetime import datetime

from trading_system.research.contracts import ResearchRow, WalkForwardFold
from trading_system.research.orchestration import (
    DatasetPartition,
    ExperimentStage,
    assign_fold_rows,
    symbol_holdout_bucket,
    transition,
)
from trading_system.research.registry import ExperimentRegistry


class ExperimentWorkflow:
    def __init__(self, registry: ExperimentRegistry, experiment_id: str) -> None:
        self.registry = registry
        self.experiment_id = experiment_id

    @property
    def stage(self) -> ExperimentStage:
        return self.registry.current_stage(self.experiment_id)

    def assign(
        self, fold: WalkForwardFold, rows: tuple[ResearchRow, ...]
    ) -> int:
        inserted = 0
        for item in assign_fold_rows(self.experiment_id, fold, rows):
            inserted += int(self.registry.insert_fold_assignment(item))
            if item.partition is DatasetPartition.EXCLUDED:
                inserted += int(self.registry.insert_exclusion(item))
        for symbol in sorted({row.symbol for row in rows}):
            inserted += int(
                self.registry.insert_holdout(
                    self.experiment_id, symbol, symbol_holdout_bucket(symbol)
                )
            )
        return inserted

    def advance(
        self,
        new_stage: ExperimentStage,
        *,
        frozen_definition_hash: str | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        item = transition(
            self.experiment_id,
            self.stage,
            new_stage,
            frozen_definition_hash=frozen_definition_hash,
            occurred_at=occurred_at,
        )
        return self.registry.insert_transition(item)
