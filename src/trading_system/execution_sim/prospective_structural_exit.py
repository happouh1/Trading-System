"""Offline structural-damage next-open exit with receipt-time availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from trading_system.domain import Candle
from trading_system.serialization import deterministic_id

VERSION = "PROSPECTIVE_STRUCTURAL_EXIT.1.0"


@dataclass(frozen=True, slots=True)
class StructuralExitAssessment:
    assessment_id: str
    trade_id: str
    symbol: str
    signal_candle_id: str
    source_candle_id: str
    event_time: datetime
    known_at: datetime
    status: str
    fill_price: Decimal
    qualifying_completed_trade: bool = field(default=False, init=False)
    broker_write_performed: bool = field(default=False, init=False)
    fees_status: str = field(default="NOT_MODELLED", init=False)


def assess_structural_exit(
    *, trade_id: str, symbol: str, signal_candle_id: str,
    signal_known_at: datetime, signal_damage_score: Decimal, candle: Candle,
    atr20: Decimal, feature_known_at: datetime, adjustment_factor: Decimal,
    received_at: datetime, as_of: datetime,
) -> StructuralExitAssessment:
    for value in (signal_known_at, feature_known_at, received_at, as_of):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("UTC timestamps required")
    if (
        not trade_id or not signal_candle_id or symbol == "AAPL" or candle.symbol != symbol
        or not candle.is_complete or signal_known_at > candle.open_time
        or feature_known_at > candle.open_time
        or not candle.close_time <= received_at <= as_of
        or candle.adjustment_factor != adjustment_factor
        or not signal_damage_score.is_finite() or signal_damage_score < 70
        or any(not value.is_finite() or value <= 0 for value in (
            candle.open, atr20, adjustment_factor,
        ))
    ):
        raise ValueError("invalid or unavailable structural-exit evidence")
    with localcontext() as context:
        context.prec = 50
        slippage = max(candle.open / Decimal(10000), Decimal("0.02") * atr20)
        fill = candle.open - slippage
    if not fill.is_finite() or fill <= 0:
        raise ValueError("nonpositive modelled structural-exit fill")
    identity = (
        VERSION, trade_id, symbol, signal_candle_id, signal_known_at,
        signal_damage_score, candle, atr20, feature_known_at,
        adjustment_factor, received_at,
    )
    return StructuralExitAssessment(
        deterministic_id("sim_structural_exit", identity), trade_id, symbol,
        signal_candle_id, candle.candle_id, candle.open_time, received_at,
        "STRUCTURAL_DAMAGE_EXIT_MODELLED", fill,
    )
