"""Versioned future outcome labels kept outside decision code paths."""

from __future__ import annotations

from decimal import Decimal

from trading_system.domain import Candle, Direction, Outcome
from trading_system.serialization import deterministic_id


def label_outcome(
    *,
    run_id: str,
    observation_id: str,
    label_version: str,
    direction: Direction,
    entry: Decimal,
    risk: Decimal,
    future_candles: tuple[Candle, ...],
) -> Outcome:
    if direction is Direction.NONE:
        raise ValueError("outcome direction must be LONG or SHORT")
    if entry <= 0 or risk <= 0 or not future_candles:
        raise ValueError("entry, risk, and future candles are required")
    if any(not candle.is_complete for candle in future_candles):
        raise ValueError("outcome labels require completed future candles")
    if tuple(c.close_time for c in future_candles) != tuple(
        sorted(c.close_time for c in future_candles)
    ):
        raise ValueError("future candles must be chronological")
    sign = Decimal(1) if direction is Direction.LONG else Decimal(-1)
    favorable = tuple(
        sign * ((candle.high if direction is Direction.LONG else candle.low) - entry) / risk
        for candle in future_candles
    )
    adverse = tuple(
        sign * (entry - (candle.low if direction is Direction.LONG else candle.high)) / risk
        for candle in future_candles
    )
    mfe = max(Decimal(0), *favorable)
    mae = max(Decimal(0), *adverse)
    time_to_1r = next((index for index, value in enumerate(favorable, 1) if value >= 1), None)
    time_to_2r = next((index for index, value in enumerate(favorable, 1) if value >= 2), None)
    time_to_loss = next((index for index, value in enumerate(adverse, 1) if value >= 1), None)
    success = time_to_2r is not None and (time_to_loss is None or time_to_2r < time_to_loss)
    label = "GENERIC_SUCCESS" if success else "GENERIC_FAILURE"
    horizon = len(future_candles)
    return Outcome(
        outcome_id=deterministic_id(
            "outcome", (run_id, observation_id, label_version, horizon)
        ),
        run_id=run_id,
        observation_id=observation_id,
        label_version=label_version,
        horizon_bars=horizon,
        label_available_at=future_candles[-1].close_time,
        forward_return=sign * (future_candles[-1].close - entry) / entry,
        mfe_r=mfe,
        mae_r=mae,
        time_to_1r=time_to_1r,
        time_to_2r=time_to_2r,
        outcome_label=label,
    )
