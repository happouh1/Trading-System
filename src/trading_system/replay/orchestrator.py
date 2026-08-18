"""Persisted Phase 1D replay orchestration over completed source candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_system.domain import Candle
from trading_system.persistence import SQLiteRepository
from trading_system.replay.engine import ReplayCheckpoint, ReplayEngine
from trading_system.replay.lifecycle import ReplayTradeLifecycle
from trading_system.replay.narrative import CausalNarrativePipeline
from trading_system.replay.outcomes import ReplayOutcomeTracker


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    processed_candles: int
    emitted_observations: int
    emitted_decisions: int
    checkpoint: ReplayCheckpoint | None


class ReplayOrchestrator:
    """Run causal features and an explained decision for every selected candle."""

    def __init__(
        self,
        run_id: str,
        repository: SQLiteRepository,
        *,
        normalized_risk_budget: Decimal = Decimal(1000),
    ) -> None:
        self.run_id = run_id
        self.repository = repository
        metadata = repository.run_metadata(run_id)
        if metadata is None:
            raise ValueError("run must be persisted before replay")
        code_version, config_hash, _data, _calendar, _seed = metadata
        self.pipeline = CausalNarrativePipeline(run_id, config_hash, code_version)
        self.lifecycle = ReplayTradeLifecycle(
            run_id, normalized_risk_budget=normalized_risk_budget
        )
        self.outcomes = ReplayOutcomeTracker(run_id)

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
                    self.lifecycle.before_bar(candle)
                    narrative = self.pipeline.push(
                        candle,
                        position_already_open=self.lifecycle.has_exposure(candle),
                    )
                    self.lifecycle.after_bar(
                        candle,
                        narrative.decision,
                        narrative.candidates,
                        narrative.observation,
                        narrative.structure.confirmed_swings,
                    )
                    self.outcomes.push(candle, narrative.decision)

        def evaluate(candle: Candle) -> object:
            nonlocal observations, decisions
            trade_events, completed_trades = self.lifecycle.before_bar(candle)
            narrative = self.pipeline.push(
                candle,
                position_already_open=self.lifecycle.has_exposure(candle),
            )
            self.repository.insert_candle(candle)
            self.repository.insert_snapshot(narrative.observation)
            for level in narrative.levels:
                self.repository.insert_level(level)
            for pattern_event in narrative.pattern_events:
                self.repository.insert_pattern_event(pattern_event)
            self.repository.insert_decision(narrative.decision)
            later_events, later_trades = self.lifecycle.after_bar(
                candle,
                narrative.decision,
                narrative.candidates,
                narrative.observation,
                narrative.structure.confirmed_swings,
            )
            outcomes = self.outcomes.push(candle, narrative.decision)
            for trade_event in (*trade_events, *later_events):
                self.repository.insert_trade_event(trade_event)
            for trade in (*completed_trades, *later_trades):
                self.repository.insert_completed_trade(trade)
            for outcome in outcomes:
                self.repository.insert_outcome(outcome)
            observations += 1
            decisions += 1
            return {
                "observation_id": narrative.observation.observation_id,
                "pattern_event_ids": tuple(
                    event.event_id for event in narrative.pattern_events
                ),
                "decision_id": narrative.decision.decision_id,
                "trade_event_ids": tuple(
                    event.trade_event_id for event in (*trade_events, *later_events)
                ),
                "completed_trade_ids": tuple(
                    trade.trade_id for trade in (*completed_trades, *later_trades)
                ),
                "outcome_ids": tuple(outcome.outcome_id for outcome in outcomes),
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
