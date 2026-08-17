"""Persisted Phase 1D replay orchestration over completed source candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system.decisions import DecisionEngine
from trading_system.domain import Candle
from trading_system.features import CausalFeatureEngine
from trading_system.persistence import SQLiteRepository
from trading_system.replay.engine import ReplayCheckpoint, ReplayEngine


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    processed_candles: int
    emitted_observations: int
    emitted_decisions: int
    checkpoint: ReplayCheckpoint | None


class ReplayOrchestrator:
    """Run causal features and an explained decision for every selected candle."""

    def __init__(self, run_id: str, repository: SQLiteRepository) -> None:
        self.run_id = run_id
        self.repository = repository
        self.features = CausalFeatureEngine(run_id)
        self.decisions = DecisionEngine(run_id)

    def run(
        self,
        candles: tuple[Candle, ...],
        *,
        resume_after: datetime | None = None,
        processed_before: int = 0,
        prior_state_hash: str = "GENESIS",
    ) -> ReplaySummary:
        observations = 0
        decisions = 0

        if resume_after is not None:
            for candle in ReplayEngine.normalize(candles):
                if candle.close_time <= resume_after:
                    self.features.push(candle)

        def evaluate(candle: Candle) -> object:
            nonlocal observations, decisions
            observation = self.features.push(candle)
            decision = self.decisions.decide(
                observation.observation_id,
                observation.known_at,
                (),
            )
            self.repository.insert_candle(candle)
            self.repository.insert_snapshot(observation)
            self.repository.insert_decision(decision)
            observations += 1
            decisions += 1
            return {
                "observation_id": observation.observation_id,
                "decision_id": decision.decision_id,
            }

        records, checkpoint = ReplayEngine(evaluate).run(
            candles,
            resume_after=resume_after,
            processed_before=processed_before,
            prior_state_hash=prior_state_hash,
        )
        if checkpoint is not None:
            self.repository.save_checkpoint(
                self.run_id,
                checkpoint.last_close_time,
                checkpoint.processed_candles,
                checkpoint.state_hash,
            )
        return ReplaySummary(len(records), observations, decisions, checkpoint)
