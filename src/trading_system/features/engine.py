"""Streaming causal feature engine with explicit full-window warm-up."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from trading_system.domain import Candle, Observation, Timeframe
from trading_system.serialization import canonical_hash, deterministic_id

_NEW_YORK = ZoneInfo("America/New_York")
_ZERO = Decimal(0)
_ONE = Decimal(1)


@dataclass(slots=True)
class _SeriesState:
    last_time: datetime | None = None
    previous_close: Decimal | None = None
    candle_ids: list[str] = field(default_factory=list)
    closes: list[Decimal] = field(default_factory=list)
    true_ranges: list[Decimal] = field(default_factory=list)
    atr: Decimal | None = None
    ema: dict[int, Decimal] = field(default_factory=dict)
    ema_history: dict[int, list[Decimal]] = field(default_factory=lambda: defaultdict(list))
    slot_volumes: dict[str, list[Decimal]] = field(default_factory=lambda: defaultdict(list))


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, _ZERO) / Decimal(len(values))


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _slot(candle: Candle) -> str:
    local = candle.open_time.astimezone(_NEW_YORK)
    if candle.timeframe in (Timeframe.HOUR_1, Timeframe.HOUR_4):
        return f"{local.hour:02d}:{local.minute:02d}"
    return candle.timeframe.value


class CausalFeatureEngine:
    """Stateful per-symbol/timeframe calculator that never reads future bars."""

    def __init__(
        self,
        run_id: str,
        *,
        atr_period: int = 20,
        adr_period: int = 20,
        rvol_period: int = 20,
        ema_periods: tuple[int, ...] = (10, 20, 50),
        sma_period: int = 200,
        ema_slope_lookback: int = 5,
        schema_version: str = "1.1.0",
    ) -> None:
        periods = (
            atr_period,
            adr_period,
            rvol_period,
            sma_period,
            ema_slope_lookback,
            *ema_periods,
        )
        if any(period <= 0 for period in periods):
            raise ValueError("feature periods must be positive")
        self.run_id = run_id
        self.atr_period = atr_period
        self.adr_period = adr_period
        self.rvol_period = rvol_period
        self.ema_periods = ema_periods
        self.sma_period = sma_period
        self.ema_slope_lookback = ema_slope_lookback
        self.schema_version = schema_version
        self._states: dict[tuple[str, Timeframe], _SeriesState] = {}
        self._daily_ranges: dict[str, list[tuple[date, Decimal, str]]] = defaultdict(list)

    def _adr(self, candle: Candle) -> Decimal | None:
        prior = [
            day_range
            for session_date, day_range, _candle_id in self._daily_ranges[candle.symbol]
            if session_date < candle.session_date
        ]
        if len(prior) < self.adr_period:
            return None
        return _mean(prior[-self.adr_period :])

    def _ema(self, state: _SeriesState, period: int, close: Decimal) -> Decimal | None:
        count = len(state.closes)
        if count < period:
            return None
        if count == period:
            result = _mean(state.closes[-period:])
        else:
            prior = state.ema[period]
            alpha = Decimal(2) / Decimal(period + 1)
            result = prior + alpha * (close - prior)
        state.ema[period] = result
        return result

    def push(self, candle: Candle) -> Observation:
        if not candle.is_complete:
            raise ValueError("features are available only for completed candles")
        key = (candle.symbol, candle.timeframe)
        state = self._states.setdefault(key, _SeriesState())
        if state.last_time is not None and candle.close_time <= state.last_time:
            raise ValueError("candles must be pushed in strictly increasing close-time order")
        with localcontext() as context:
            context.prec = 34
            candle_range = candle.high - candle.low
            body = abs(candle.close - candle.open)
            upper_wick = candle.high - max(candle.open, candle.close)
            lower_wick = min(candle.open, candle.close) - candle.low
            clv = (candle.close - candle.low) / max(candle_range, Decimal("1e-12"))
            signed_clv = Decimal(2) * clv - _ONE
            if state.previous_close is None:
                true_range = candle_range
            else:
                true_range = max(
                    candle_range,
                    abs(candle.high - state.previous_close),
                    abs(candle.low - state.previous_close),
                )
            state.closes.append(candle.close)
            state.candle_ids.append(candle.candle_id)
            state.true_ranges.append(true_range)
            if len(state.true_ranges) == self.atr_period:
                state.atr = _mean(state.true_ranges[-self.atr_period :])
            elif len(state.true_ranges) > self.atr_period:
                assert state.atr is not None
                state.atr = (
                    state.atr * Decimal(self.atr_period - 1) + true_range
                ) / Decimal(self.atr_period)
            ema_values = {
                f"ema{period}": self._ema(state, period, candle.close)
                for period in self.ema_periods
            }
            sma = (
                _mean(state.closes[-self.sma_period :])
                if len(state.closes) >= self.sma_period
                else None
            )
            adr = self._adr(candle)
            slope_values: dict[str, Decimal | None] = {}
            for period in self.ema_periods:
                value = ema_values[f"ema{period}"]
                history = state.ema_history[period]
                slope: Decimal | None = None
                if value is not None:
                    if adr is not None and len(history) >= self.ema_slope_lookback:
                        slope = (value - history[-self.ema_slope_lookback]) / (
                            Decimal(self.ema_slope_lookback) * adr
                        )
                    history.append(value)
                slope_values[f"ema{period}_slope_adr"] = slope
            slot = _slot(candle)
            prior_volumes = state.slot_volumes[slot]
            rvol = None
            if len(prior_volumes) >= self.rvol_period:
                baseline = _median(prior_volumes[-self.rvol_period :])
                rvol = candle.volume / baseline if baseline > 0 else None
            prior_volumes.append(candle.volume)
            features: dict[str, object] = {
                "range": candle_range,
                "body": body,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "clv": clv,
                "signed_clv": signed_clv,
                "true_range": true_range,
                "atr20": state.atr,
                "adr20": adr,
                "rvol20": rvol,
                "sma200": sma,
                "volume_slot": slot,
                **ema_values,
                **slope_values,
            }
            missing = tuple(sorted(name for name, value in features.items() if value is None))
            fingerprint = canonical_hash(
                {
                    "candle_id": candle.candle_id,
                    "series_candle_ids": tuple(state.candle_ids),
                    "prior_daily_candle_ids": tuple(
                        candle_id
                        for session_date, _day_range, candle_id in self._daily_ranges[candle.symbol]
                        if session_date < candle.session_date
                    ),
                    "previous_candle_close_time": state.last_time,
                    "periods": {
                        "atr": self.atr_period,
                        "adr": self.adr_period,
                        "rvol": self.rvol_period,
                        "ema": self.ema_periods,
                        "sma": self.sma_period,
                        "ema_slope_lookback": self.ema_slope_lookback,
                    },
                }
            )
            observation_id = deterministic_id(
                "observation",
                (self.run_id, candle.candle_id, self.schema_version, fingerprint),
            )
            observation = Observation(
                observation_id=observation_id,
                run_id=self.run_id,
                candle_id=candle.candle_id,
                known_at=candle.close_time,
                schema_version=self.schema_version,
                input_fingerprint=fingerprint,
                features=features,
                data_quality={"complete": True, "warmup_missing": missing},
            )
            state.previous_close = candle.close
            state.last_time = candle.close_time
            if candle.timeframe is Timeframe.DAY_1:
                self._daily_ranges[candle.symbol].append(
                    (candle.session_date, candle_range, candle.candle_id)
                )
            return observation
