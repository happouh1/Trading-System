"""Causal deferred outcome labeling for directional replay decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from trading_system.domain import Candle, Decision, DecisionAction, Outcome, Timeframe
from trading_system.learning import label_outcome


@dataclass(slots=True)
class _PendingOutcome:
    observation_id: str
    decision: Decision
    candles: list[Candle] = field(default_factory=list)


class ReplayOutcomeTracker:
    """Emit labels only when the configured future completed bars exist."""

    _HORIZONS: ClassVar[dict[Timeframe, tuple[int, ...]]] = {
        Timeframe.HOUR_1: (1, 3, 6, 12, 24, 48),
        Timeframe.HOUR_4: (1, 3, 6, 12, 24),
    }

    def __init__(self, run_id: str, *, label_version: str = "1.0.0") -> None:
        self.run_id = run_id
        self.label_version = label_version
        self._pending: dict[tuple[str, Timeframe], list[_PendingOutcome]] = {}

    def push(self, candle: Candle, decision: Decision) -> tuple[Outcome, ...]:
        key = (candle.symbol, candle.timeframe)
        horizons = self._HORIZONS.get(candle.timeframe, ())
        emitted: list[Outcome] = []
        tasks = self._pending.setdefault(key, [])
        retained: list[_PendingOutcome] = []
        for task in tasks:
            task.candles.append(candle)
            count = len(task.candles)
            if count in horizons:
                plan = task.decision.entry_plan
                assert plan is not None
                emitted.append(
                    label_outcome(
                        run_id=self.run_id,
                        observation_id=task.observation_id,
                        label_version=self.label_version,
                        direction=task.decision.direction,
                        entry=plan.planned_entry,
                        risk=plan.risk_per_unit,
                        future_candles=tuple(task.candles),
                    )
                )
            if horizons and count < horizons[-1]:
                retained.append(task)
        self._pending[key] = retained
        if (
            horizons
            and decision.action in {DecisionAction.LONG, DecisionAction.SHORT}
            and decision.entry_plan is not None
        ):
            self._pending[key].append(
                _PendingOutcome(decision.observation_id, decision)
            )
        return tuple(emitted)
