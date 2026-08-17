"""Portfolio-independent trade statistics in R multiples."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TradeResult:
    trade_id: str
    net_r: Decimal
    mfe_r: Decimal
    mae_r: Decimal
    hold_bars: int
    gross_r: Decimal | None = None


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    trade_count: int
    win_rate: Decimal
    expectancy_r: Decimal
    gross_expectancy_r: Decimal
    profit_factor: Decimal | None
    median_mfe_r: Decimal
    median_mae_r: Decimal
    maximum_drawdown_r: Decimal
    average_hold_bars: Decimal


def _median(values: tuple[Decimal, ...]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def summarize(trades: tuple[TradeResult, ...]) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(
            0,
            Decimal(0),
            Decimal(0),
            Decimal(0),
            None,
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
        )
    count = Decimal(len(trades))
    wins = tuple(trade.net_r for trade in trades if trade.net_r > 0)
    losses = tuple(trade.net_r for trade in trades if trade.net_r < 0)
    gross_profit = sum(wins, Decimal(0))
    gross_loss = abs(sum(losses, Decimal(0)))
    equity = peak = drawdown = Decimal(0)
    for trade in trades:
        equity += trade.net_r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return BacktestMetrics(
        len(trades),
        Decimal(len(wins)) / count,
        sum((trade.net_r for trade in trades), Decimal(0)) / count,
        sum(
            (trade.gross_r if trade.gross_r is not None else trade.net_r for trade in trades),
            Decimal(0),
        )
        / count,
        gross_profit / gross_loss if gross_loss else None,
        _median(tuple(trade.mfe_r for trade in trades)),
        _median(tuple(trade.mae_r for trade in trades)),
        drawdown,
        Decimal(sum(trade.hold_bars for trade in trades)) / count,
    )
