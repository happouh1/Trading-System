"""Persisted Phase 1D replay orchestration over completed source candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system.domain import Candle
from trading_system.persistence import SQLiteRepository
from trading_system.replay.engine import ReplayCheckpoint, ReplayEngine
from trading_system.replay.narrative import CausalNarrativePipeline


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
        metadata = repository.run_metadata(run_id)
        if metadata is None:
            raise ValueError("run must be persisted before replay")
        code_version, config_hash, _data, _calendar, _seed = metadata
        self.pipeline = CausalNarrativePipeline(run_id, config_hash, code_version)

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
                    self.pipeline.push(candle)

        def evaluate(candle: Candle) -> object:
            nonlocal observations, decisions
            narrative = self.pipeline.push(candle)
            self.repository.insert_candle(candle)
            self.repository.insert_snapshot(narrative.observation)
            for level in narrative.levels:
                self.repository.insert_level(level)
            for event in narrative.pattern_events:
                self.repository.insert_pattern_event(event)
            self.repository.insert_decision(narrative.decision)
            observations += 1
            decisions += 1
            return {
                "observation_id": narrative.observation.observation_id,
                "pattern_event_ids": tuple(
                    event.event_id for event in narrative.pattern_events
                ),
                "decision_id": narrative.decision.decision_id,
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
