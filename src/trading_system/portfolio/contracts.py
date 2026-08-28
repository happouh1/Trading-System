"""Immutable Phase 4A portfolio-research contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Direction
from trading_system.serialization import canonical_json, deterministic_id


class StrategyClass(StrEnum):
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    POSITION = "POSITION"
    LONG_TERM_RESEARCH = "LONG_TERM_RESEARCH"


class PortfolioAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class PortfolioCandidate:
    candidate_id: str
    trade_plan_id: str
    symbol: str
    direction: Direction
    known_at: datetime
    planned_hold_sessions: int
    entry_price: Decimal
    stop_price: Decimal
    quantity: Decimal
    average_daily_dollar_volume: Decimal
    sector: str
    source_revision: str

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.trade_plan_id or not self.source_revision:
            raise ValueError("candidate identity and provenance are required")
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be nonempty uppercase text")
        if self.direction is Direction.NONE:
            raise ValueError("portfolio candidate must be directional")
        _aware(self.known_at, "known_at")
        if (
            not isinstance(self.planned_hold_sessions, int)
            or isinstance(self.planned_hold_sessions, bool)
            or self.planned_hold_sessions <= 0
        ):
            raise ValueError("planned_hold_sessions must be positive")
        for name in ("entry_price", "stop_price", "quantity"):
            _positive(getattr(self, name), name)
        if (
            not self.average_daily_dollar_volume.is_finite()
            or self.average_daily_dollar_volume < 0
        ):
            raise ValueError("average_daily_dollar_volume must be finite and nonnegative")
        if self.direction is Direction.LONG and self.stop_price >= self.entry_price:
            raise ValueError("long candidate stop must be below entry")
        if self.direction is Direction.SHORT and self.stop_price <= self.entry_price:
            raise ValueError("short candidate stop must be above entry")
        if not self.sector:
            raise ValueError("point-in-time sector is required")

    @property
    def notional(self) -> Decimal:
        return self.entry_price * self.quantity

    @property
    def risk_amount(self) -> Decimal:
        return abs(self.entry_price - self.stop_price) * self.quantity

    @property
    def volume_participation(self) -> Decimal | None:
        if self.average_daily_dollar_volume == 0:
            return None
        return self.notional / self.average_daily_dollar_volume


@dataclass(frozen=True, slots=True)
class PortfolioPosition:
    position_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    mark_price: Decimal
    stop_price: Decimal
    sector: str
    strategy_class: StrategyClass

    def __post_init__(self) -> None:
        if not self.position_id or not self.symbol or not self.sector:
            raise ValueError("position identity fields are required")
        if self.direction is Direction.NONE:
            raise ValueError("portfolio position must be directional")
        for name in ("quantity", "mark_price", "stop_price"):
            _positive(getattr(self, name), name)
        if self.direction is Direction.LONG and self.stop_price >= self.mark_price:
            raise ValueError("long position stop must be below its mark")
        if self.direction is Direction.SHORT and self.stop_price <= self.mark_price:
            raise ValueError("short position stop must be above its mark")

    @property
    def notional(self) -> Decimal:
        return self.mark_price * self.quantity


@dataclass(frozen=True, slots=True)
class PortfolioState:
    portfolio_id: str
    as_of: datetime
    equity: Decimal
    positions: tuple[PortfolioPosition, ...] = ()
    pending_symbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.portfolio_id:
            raise ValueError("portfolio_id is required")
        _aware(self.as_of, "as_of")
        _positive(self.equity, "equity")
        if len(set(self.pending_symbols)) != len(self.pending_symbols):
            raise ValueError("pending symbols must be unique")
        if any(not symbol or symbol != symbol.upper() for symbol in self.pending_symbols):
            raise ValueError("pending symbols must be uppercase")
        position_symbols = tuple(position.symbol for position in self.positions)
        if len(set(position_symbols)) != len(position_symbols):
            raise ValueError("portfolio state cannot contain duplicate position symbols")
        if set(position_symbols) & set(self.pending_symbols):
            raise ValueError("a symbol cannot be both open and pending")


@dataclass(frozen=True, slots=True)
class PortfolioAssessment:
    assessment_id: str
    portfolio_id: str
    candidate_id: str
    known_at: datetime
    strategy_class: StrategyClass
    action: PortfolioAction
    reason_codes: tuple[str, ...]
    proposed_gross_exposure_pct: Decimal
    proposed_net_exposure_pct: Decimal
    proposed_position_exposure_pct: Decimal
    proposed_sector_exposure_pct: Decimal
    proposed_risk_pct: Decimal
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.known_at, "known_at")
        if not self.assessment_id or not self.portfolio_id or not self.candidate_id:
            raise ValueError("assessment identity fields are required")
        if not self.config_hash:
            raise ValueError("config_hash is required")
        if self.action is PortfolioAction.REJECT and not self.reason_codes:
            raise ValueError("rejected assessment requires reason codes")
        for name in (
            "proposed_gross_exposure_pct",
            "proposed_position_exposure_pct",
            "proposed_sector_exposure_pct",
            "proposed_risk_pct",
        ):
            value = getattr(self, name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not self.proposed_net_exposure_pct.is_finite():
            raise ValueError("proposed_net_exposure_pct must be finite")

    @classmethod
    def create(
        cls,
        *,
        portfolio_id: str,
        candidate_id: str,
        known_at: datetime,
        strategy_class: StrategyClass,
        action: PortfolioAction,
        reason_codes: tuple[str, ...],
        proposed_gross_exposure_pct: Decimal,
        proposed_net_exposure_pct: Decimal,
        proposed_position_exposure_pct: Decimal,
        proposed_sector_exposure_pct: Decimal,
        proposed_risk_pct: Decimal,
        config_hash: str,
    ) -> PortfolioAssessment:
        identity = (
            portfolio_id,
            candidate_id,
            known_at,
            config_hash,
            action,
            reason_codes,
        )
        return cls(
            deterministic_id("portfolio_assessment", identity),
            portfolio_id,
            candidate_id,
            known_at,
            strategy_class,
            action,
            reason_codes,
            proposed_gross_exposure_pct,
            proposed_net_exposure_pct,
            proposed_position_exposure_pct,
            proposed_sector_exposure_pct,
            proposed_risk_pct,
            config_hash,
        )

    def to_json(self) -> str:
        return canonical_json(self)
