"""Deterministic Phase 4A strategy classification and portfolio gates."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from trading_system.domain import Direction
from trading_system.portfolio.config import PortfolioConfig
from trading_system.portfolio.contracts import (
    PortfolioAction,
    PortfolioAssessment,
    PortfolioCandidate,
    PortfolioPosition,
    PortfolioState,
    StrategyClass,
)
from trading_system.serialization import deterministic_id


def classify_strategy(planned_hold_sessions: int, config: PortfolioConfig) -> StrategyClass:
    if planned_hold_sessions <= 0:
        raise ValueError("planned_hold_sessions must be positive")
    intraday = config.integer("classification", "intraday_max_sessions")
    swing = config.integer("classification", "swing_max_sessions")
    position = config.integer("classification", "position_max_sessions")
    if planned_hold_sessions <= intraday:
        return StrategyClass.INTRADAY
    if planned_hold_sessions <= swing:
        return StrategyClass.SWING
    if planned_hold_sessions <= position:
        return StrategyClass.POSITION
    return StrategyClass.LONG_TERM_RESEARCH


class PortfolioEngine:
    def __init__(self, config: PortfolioConfig) -> None:
        self.config = config

    def assess(
        self, state: PortfolioState, candidate: PortfolioCandidate
    ) -> PortfolioAssessment:
        if candidate.known_at != state.as_of:
            raise ValueError("candidate and portfolio state must share the exact as-of timestamp")
        strategy = classify_strategy(candidate.planned_hold_sessions, self.config)
        equity = state.equity
        existing_notionals = tuple(position.notional for position in state.positions)
        existing_signed = tuple(
            value if position.direction is Direction.LONG else -value
            for position, value in zip(state.positions, existing_notionals, strict=True)
        )
        candidate_signed = (
            candidate.notional
            if candidate.direction is Direction.LONG
            else -candidate.notional
        )
        gross = (sum(existing_notionals, Decimal(0)) + candidate.notional) / equity
        net = (sum(existing_signed, Decimal(0)) + candidate_signed) / equity
        position_pct = candidate.notional / equity
        sector_pct = (
            sum(
                (
                    position.notional
                    for position in state.positions
                    if position.sector == candidate.sector
                ),
                Decimal(0),
            )
            + candidate.notional
        ) / equity
        risk_pct = candidate.risk_amount / equity

        reasons: list[str] = []
        symbols = {position.symbol for position in state.positions} | set(state.pending_symbols)
        if candidate.symbol in symbols:
            reasons.append("PORTFOLIO_DUPLICATE_SYMBOL")
        if len(state.positions) >= self.config.integer("exposure", "maximum_positions"):
            reasons.append("PORTFOLIO_MAX_POSITIONS")
        if strategy is StrategyClass.LONG_TERM_RESEARCH:
            reasons.append("LONG_TERM_FUNDAMENTALS_REQUIRED")

        liquidity = self.config.section("liquidity")
        if candidate.entry_price < self.config.decimal("liquidity", "minimum_price"):
            reasons.append("LIQUIDITY_PRICE_BELOW_MINIMUM")
        if candidate.average_daily_dollar_volume < self.config.decimal(
            "liquidity", "minimum_average_daily_dollar_volume"
        ):
            reasons.append("LIQUIDITY_DOLLAR_VOLUME_BELOW_MINIMUM")
        participation = candidate.volume_participation
        if participation is None or participation > Decimal(
            str(liquidity["maximum_volume_participation"])
        ):
            reasons.append("LIQUIDITY_PARTICIPATION_EXCEEDED")

        exposure = self.config.section("exposure")
        limits = (
            (gross, "maximum_gross_exposure_pct", "PORTFOLIO_GROSS_EXPOSURE"),
            (abs(net), "maximum_absolute_net_exposure_pct", "PORTFOLIO_NET_EXPOSURE"),
            (position_pct, "maximum_position_exposure_pct", "PORTFOLIO_POSITION_EXPOSURE"),
            (sector_pct, "maximum_sector_exposure_pct", "PORTFOLIO_SECTOR_EXPOSURE"),
        )
        for actual, key, reason in limits:
            if actual > Decimal(str(exposure[key])):
                reasons.append(reason)
        budget = self.config.decimal("strategy_risk_budget_pct", strategy.value)
        if risk_pct > budget:
            reasons.append("STRATEGY_RISK_BUDGET")

        reason_codes = tuple(sorted(set(reasons)))
        action = PortfolioAction.REJECT if reason_codes else PortfolioAction.ACCEPT
        return PortfolioAssessment.create(
            portfolio_id=state.portfolio_id,
            candidate_id=candidate.candidate_id,
            known_at=candidate.known_at,
            strategy_class=strategy,
            action=action,
            reason_codes=reason_codes,
            proposed_gross_exposure_pct=gross,
            proposed_net_exposure_pct=net,
            proposed_position_exposure_pct=position_pct,
            proposed_sector_exposure_pct=sector_pct,
            proposed_risk_pct=risk_pct,
            config_hash=self.config.config_hash,
        )

    def apply(
        self,
        state: PortfolioState,
        candidate: PortfolioCandidate,
        assessment: PortfolioAssessment,
    ) -> PortfolioState:
        if assessment.action is not PortfolioAction.ACCEPT:
            raise ValueError("only accepted assessments may change simulated portfolio state")
        if assessment.portfolio_id != state.portfolio_id:
            raise ValueError("assessment portfolio does not match state")
        if assessment.candidate_id != candidate.candidate_id:
            raise ValueError("assessment candidate does not match input")
        if assessment.config_hash != self.config.config_hash:
            raise ValueError("assessment configuration does not match engine")
        position = PortfolioPosition(
            deterministic_id("portfolio_position", (state.portfolio_id, candidate.candidate_id)),
            candidate.symbol,
            candidate.direction,
            candidate.quantity,
            candidate.entry_price,
            candidate.stop_price,
            candidate.sector,
            assessment.strategy_class,
        )
        return replace(state, positions=(*state.positions, position))

    def simulate(
        self,
        state: PortfolioState,
        candidates: tuple[PortfolioCandidate, ...],
    ) -> tuple[PortfolioState, tuple[PortfolioAssessment, ...]]:
        ordered = tuple(sorted(candidates, key=lambda item: (item.known_at, item.candidate_id)))
        if ordered != candidates:
            raise ValueError("portfolio candidates must be ordered by known_at and candidate_id")
        assessments: list[PortfolioAssessment] = []
        current = state
        for candidate in candidates:
            if candidate.known_at != current.as_of:
                raise ValueError("Phase 4A batch candidates must share the portfolio as-of")
            assessment = self.assess(current, candidate)
            assessments.append(assessment)
            if assessment.action is PortfolioAction.ACCEPT:
                current = self.apply(current, candidate, assessment)
        return current, tuple(assessments)
