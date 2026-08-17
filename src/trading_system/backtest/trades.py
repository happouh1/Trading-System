"""Normalized completed trade construction and cost-aware R results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_system.backtest.metrics import TradeResult
from trading_system.domain import Direction, Timeframe


@dataclass(frozen=True, slots=True)
class CompletedTrade:
    trade_id: str
    run_id: str
    symbol: str
    timeframe: Timeframe
    direction: Direction
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    initial_risk: Decimal
    gross_r: Decimal
    net_r: Decimal
    mfe_r: Decimal
    mae_r: Decimal
    hold_bars: int
    total_cost: Decimal

    def __post_init__(self) -> None:
        if self.direction is Direction.NONE:
            raise ValueError("completed trade direction cannot be NONE")
        if self.entry_time.tzinfo is None or self.exit_time.tzinfo is None:
            raise ValueError("trade timestamps must be timezone-aware")
        if self.exit_time < self.entry_time:
            raise ValueError("exit cannot precede entry")
        if min(self.entry_price, self.exit_price, self.initial_risk) <= 0:
            raise ValueError("trade prices and initial risk must be positive")
        if min(self.mfe_r, self.mae_r, self.total_cost) < 0 or self.hold_bars < 0:
            raise ValueError("excursions, costs, and hold bars must be nonnegative")

    def result(self) -> TradeResult:
        return TradeResult(
            self.trade_id,
            self.net_r,
            self.mfe_r,
            self.mae_r,
            self.hold_bars,
            self.gross_r,
        )


def complete_trade(
    *,
    trade_id: str,
    run_id: str,
    symbol: str,
    timeframe: Timeframe,
    direction: Direction,
    entry_time: datetime,
    exit_time: datetime,
    entry_price: Decimal,
    exit_price: Decimal,
    initial_risk: Decimal,
    favorable_extreme: Decimal,
    adverse_extreme: Decimal,
    hold_bars: int,
    total_cost: Decimal = Decimal(0),
) -> CompletedTrade:
    if initial_risk <= 0:
        raise ValueError("initial risk must be positive")
    sign = Decimal(1) if direction is Direction.LONG else Decimal(-1)
    gross_r = sign * (exit_price - entry_price) / initial_risk
    net_r = (sign * (exit_price - entry_price) - total_cost) / initial_risk
    mfe_r = max(Decimal(0), sign * (favorable_extreme - entry_price) / initial_risk)
    mae_r = max(Decimal(0), sign * (entry_price - adverse_extreme) / initial_risk)
    return CompletedTrade(
        trade_id,
        run_id,
        symbol,
        timeframe,
        direction,
        entry_time,
        exit_time,
        entry_price,
        exit_price,
        initial_risk,
        gross_r,
        net_r,
        mfe_r,
        mae_r,
        hold_bars,
        total_cost,
    )
