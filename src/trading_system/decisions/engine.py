"""Phase 1C trade gates, conflict priority, and explained outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_system.domain import (
    Decision,
    DecisionAction,
    Direction,
    PatternEvent,
    PatternState,
    RuleEvidence,
    TradePlan,
    TradeStyle,
)
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class DecisionCandidate:
    event: PatternEvent
    setup_quality: Decimal
    entry_quality: Decimal
    confidence: Decimal
    mtf_score: Decimal
    adr_utilization: Decimal
    stop_distance_adr: Decimal | None
    runway_adr: Decimal | None
    reward_risk: Decimal | None
    plan: TradePlan | None
    trigger_confirmed: bool
    critical_features_complete: bool = True
    contradictory_higher_priority: bool = False
    position_already_open: bool = False
    timeframe_states: tuple[tuple[str, str], ...] = ()


class DecisionEngine:
    def __init__(
        self,
        run_id: str,
        *,
        trade_confidence: Decimal = Decimal(75),
        watch_confidence: Decimal = Decimal(60),
        conflict_tolerance: Decimal = Decimal(5),
    ) -> None:
        self.run_id = run_id
        self.trade_confidence = trade_confidence
        self.watch_confidence = watch_confidence
        self.conflict_tolerance = conflict_tolerance

    def decide(
        self,
        observation_id: str,
        known_at: datetime,
        candidates: tuple[DecisionCandidate, ...],
    ) -> Decision:
        if not candidates:
            return self._result(
                observation_id,
                known_at,
                DecisionAction.NO_TRADE,
                Direction.NONE,
                Decimal(0),
                Decimal(0),
                Decimal(0),
                None,
                None,
                (),
                ("NO_VALID_SETUP",),
                {},
                (),
            )
        ranked = sorted(candidates, key=lambda item: (-self._priority(item), -item.confidence))
        selected = ranked[0]
        opposite = next(
            (item for item in ranked[1:] if item.event.direction is not selected.event.direction),
            None,
        )
        if (
            opposite is not None
            and self._priority(opposite) == self._priority(selected)
            and abs(opposite.confidence - selected.confidence) <= self.conflict_tolerance
        ):
            return self._candidate_result(
                observation_id,
                known_at,
                selected,
                DecisionAction.NO_TRADE,
                ("CONFLICTING_SIGNALS",),
            )
        reasons, evidence = self._gates(selected)
        if reasons:
            pending_only = set(reasons) <= {"TRIGGER_PENDING", "LOW_CONFIDENCE"}
            action = (
                DecisionAction.WATCH
                if pending_only and selected.confidence >= self.watch_confidence
                else DecisionAction.NO_TRADE
            )
            return self._candidate_result(
                observation_id, known_at, selected, action, tuple(reasons), tuple(evidence)
            )
        action = (
            DecisionAction.LONG
            if selected.event.direction is Direction.LONG
            else DecisionAction.SHORT
        )
        return self._candidate_result(
            observation_id, known_at, selected, action, (), tuple(evidence)
        )

    @staticmethod
    def _priority(candidate: DecisionCandidate) -> int:
        event = candidate.event
        if event.new_state is PatternState.TRAP_CONFIRMED:
            return 5
        if event.new_state is PatternState.ACCEPTED and event.pattern_family in {
            "BREAKOUT",
            "BREAKDOWN",
        }:
            return 4
        if event.new_state is PatternState.ACCEPTED and event.pattern_family == "RECLAIM":
            return 3
        if event.new_state is PatternState.ACCEPTED and event.pattern_family == "LIQUIDITY_SWEEP":
            return 2
        return 1

    def _gates(self, candidate: DecisionCandidate) -> tuple[list[str], list[RuleEvidence]]:
        reasons: list[str] = []
        evidence: list[RuleEvidence] = []

        def gate(
            rule: str,
            actual: object,
            operator: str,
            threshold: object,
            passed: bool,
            reason: str,
        ) -> None:
            evidence.append(RuleEvidence(rule, actual, operator, threshold, passed))
            if not passed:
                reasons.append(reason)

        gate(
            "GATE-TRIGGER",
            candidate.trigger_confirmed,
            "==",
            True,
            candidate.trigger_confirmed,
            "TRIGGER_PENDING",
        )
        gate(
            "GATE-DATA",
            candidate.critical_features_complete,
            "==",
            True,
            candidate.critical_features_complete,
            "INVALID_OR_MISSING_DATA",
        )
        valid_plan = candidate.plan is not None
        gate("GATE-PLAN", valid_plan, "==", True, valid_plan, "INVALID_OR_MISSING_DATA")
        stop = candidate.stop_distance_adr
        gate(
            "GATE-STOP-MIN",
            stop,
            ">=",
            Decimal("0.20"),
            stop is not None and stop >= Decimal("0.20"),
            "STOP_TOO_TIGHT",
        )
        gate(
            "GATE-STOP-MAX",
            stop,
            "<=",
            Decimal("1.25"),
            stop is not None and stop <= Decimal("1.25"),
            "STOP_TOO_WIDE",
        )
        runway = candidate.runway_adr
        gate(
            "GATE-RUNWAY",
            runway,
            ">=",
            Decimal("1.00"),
            runway is not None and runway >= Decimal("1.00"),
            "POOR_RUNWAY",
        )
        reward = candidate.reward_risk
        gate(
            "GATE-RR",
            reward,
            ">=",
            Decimal("1.50"),
            reward is not None and reward >= Decimal("1.50"),
            "POOR_REWARD_RISK",
        )
        utilization_cap = Decimal("1.25") if self._is_reversal(candidate) else Decimal("1.00")
        gate(
            "GATE-EXTENSION",
            candidate.adr_utilization,
            "<=",
            utilization_cap,
            candidate.adr_utilization <= utilization_cap,
            "ENTRY_EXTENDED",
        )
        gate(
            "GATE-CONFLICT",
            candidate.contradictory_higher_priority,
            "==",
            False,
            not candidate.contradictory_higher_priority,
            "CONFLICTING_SIGNALS",
        )
        gate(
            "GATE-POSITION",
            candidate.position_already_open,
            "==",
            False,
            not candidate.position_already_open,
            "POSITION_ALREADY_OPEN",
        )
        gate(
            "GATE-CONFIDENCE",
            candidate.confidence,
            ">=",
            self.trade_confidence,
            candidate.confidence >= self.trade_confidence,
            "LOW_CONFIDENCE",
        )
        return list(dict.fromkeys(reasons)), evidence

    @staticmethod
    def _is_reversal(candidate: DecisionCandidate) -> bool:
        return (
            candidate.event.new_state is PatternState.TRAP_CONFIRMED
            or candidate.event.pattern_family in {"RECLAIM", "LIQUIDITY_SWEEP"}
        )

    def _candidate_result(
        self,
        observation_id: str,
        known_at: datetime,
        candidate: DecisionCandidate,
        action: DecisionAction,
        reasons: tuple[str, ...],
        evidence: tuple[RuleEvidence, ...] = (),
    ) -> Decision:
        missing = reasons if action is DecisionAction.WATCH else ()
        rejected = reasons if action is DecisionAction.NO_TRADE else ()
        return self._result(
            observation_id,
            known_at,
            action,
            candidate.event.direction,
            candidate.setup_quality,
            candidate.entry_quality,
            candidate.confidence,
            TradeStyle.COUNTERTREND if self._is_reversal(candidate) else TradeStyle.CONTINUATION,
            candidate.plan if action in (DecisionAction.LONG, DecisionAction.SHORT) else None,
            missing,
            rejected,
            dict(candidate.timeframe_states),
            evidence,
        )

    def _result(
        self,
        observation_id: str,
        known_at: datetime,
        action: DecisionAction,
        direction: Direction,
        setup: Decimal,
        entry: Decimal,
        confidence: Decimal,
        style: TradeStyle | None,
        plan: TradePlan | None,
        missing: tuple[str, ...],
        rejected: tuple[str, ...],
        timeframe_states: dict[str, str],
        evidence: tuple[RuleEvidence, ...],
    ) -> Decision:
        identity = (self.run_id, observation_id, action, direction, confidence)
        return Decision(
            decision_id=deterministic_id("decision", identity),
            run_id=self.run_id,
            observation_id=observation_id,
            known_at=known_at,
            action=action,
            direction=direction,
            setup_quality=setup,
            entry_quality=entry,
            confidence=confidence,
            trade_style=style,
            entry_plan=plan,
            missing_conditions=missing,
            rejection_reasons=rejected,
            timeframe_states=timeframe_states,
            explanation=evidence,
        )
