"""Deterministic single-position replay lifecycle for approved Phase 1E integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from typing import cast

from trading_system.backtest import CompletedTrade, complete_trade
from trading_system.decisions import DecisionCandidate
from trading_system.domain import (
    Candle,
    Decision,
    DecisionAction,
    Direction,
    Observation,
    PatternState,
    Swing,
    SwingKind,
    TradeEvent,
    TradeEventType,
    TradePlan,
)
from trading_system.execution_sim import (
    execute_next_open,
    execute_queued_next_open_exit,
    execute_stop_exit,
)
from trading_system.risk import (
    DamageInputs,
    PositionState,
    resolve_bar_exit,
    structural_damage,
    update_trail,
)
from trading_system.serialization import deterministic_id


@dataclass(slots=True)
class _Pending:
    trade_id: str
    plan: TradePlan
    atr20: Decimal
    adr20: Decimal
    quantity: Decimal
    reference_level: Decimal


@dataclass(slots=True)
class _Open:
    trade_id: str
    plan: TradePlan
    state: PositionState
    entry_time: datetime
    quantity: Decimal
    atr20: Decimal
    adr20: Decimal
    favorable: Decimal
    adverse: Decimal
    entry_cost: Decimal
    reference_level: Decimal
    recent_closes: list[Decimal]
    prior_bar_extreme: Decimal | None = None
    queued_reason: str | None = None
    signal_candle: Candle | None = None


class ReplayTradeLifecycle:
    """Fill accepted plans on the next bar and enforce one exposure per series."""

    def __init__(
        self,
        run_id: str,
        *,
        normalized_risk_budget: Decimal = Decimal(1000),
        max_hold_bars: int = 40,
    ) -> None:
        if normalized_risk_budget <= 0:
            raise ValueError("normalized risk budget must be positive")
        self.run_id = run_id
        self.risk_budget = normalized_risk_budget
        self.max_hold_bars = max_hold_bars
        self._pending: dict[tuple[str, object], _Pending] = {}
        self._open: dict[tuple[str, object], _Open] = {}

    @staticmethod
    def _key(candle: Candle) -> tuple[str, object]:
        return candle.symbol, candle.timeframe

    def has_exposure(self, candle: Candle) -> bool:
        key = self._key(candle)
        return key in self._pending or key in self._open

    def before_bar(
        self, candle: Candle
    ) -> tuple[tuple[TradeEvent, ...], tuple[CompletedTrade, ...]]:
        key = self._key(candle)
        events: list[TradeEvent] = []
        trades: list[CompletedTrade] = []
        opened = self._open.get(key)
        if opened is not None and opened.queued_reason is not None:
            assert opened.signal_candle is not None
            result = execute_queued_next_open_exit(
                run_id=self.run_id,
                trade_id=opened.trade_id,
                state=opened.state,
                signal_candle=opened.signal_candle,
                next_candle=candle,
                atr20=opened.atr20,
                quantity=opened.quantity,
                reason=opened.queued_reason,
            )
            events.append(result.event)
            trades.append(self._complete(opened, candle, result.fill_price, result.slippage))
            del self._open[key]
            opened = None
        pending = self._pending.pop(key, None) if opened is None else None
        if pending is not None:
            result = execute_next_open(
                run_id=self.run_id,
                trade_id=pending.trade_id,
                plan=pending.plan,
                next_candle=candle,
                atr20=pending.atr20,
                adr20=pending.adr20,
                quantity=pending.quantity,
            )
            events.append(result.event)
            if result.fill_price is not None:
                risk = abs(result.fill_price - pending.plan.initial_stop)
                state = PositionState(
                    pending.plan.direction,
                    result.fill_price,
                    pending.plan.initial_stop,
                    pending.plan.initial_stop,
                    risk,
                    result.fill_price,
                )
                self._open[key] = _Open(
                    pending.trade_id,
                    pending.plan,
                    state,
                    candle.open_time,
                    pending.quantity,
                    pending.atr20,
                    pending.adr20,
                    result.fill_price,
                    result.fill_price,
                    result.slippage,
                    pending.reference_level,
                    [],
                )
        opened = self._open.get(key)
        if opened is not None:
            exit_state = resolve_bar_exit(opened.state, candle)
            if exit_state.should_exit and exit_state.reason is not None:
                result = execute_stop_exit(
                    run_id=self.run_id,
                    trade_id=opened.trade_id,
                    state=opened.state,
                    stop_candle=candle,
                    atr20=opened.atr20,
                    quantity=opened.quantity,
                )
                events.append(result.event)
                trades.append(self._complete(opened, candle, result.fill_price, result.slippage))
                del self._open[key]
        return tuple(events), tuple(trades)

    def after_bar(
        self,
        candle: Candle,
        decision: Decision,
        candidates: tuple[DecisionCandidate, ...],
        observation: Observation | None = None,
        confirmed_swings: tuple[Swing, ...] = (),
    ) -> tuple[tuple[TradeEvent, ...], tuple[CompletedTrade, ...]]:
        key = self._key(candle)
        opened = self._open.get(key)
        if opened is not None:
            opened.favorable = (
                max(opened.favorable, candle.high)
                if opened.plan.direction.value == "LONG"
                else min(opened.favorable, candle.low)
            )
            opened.adverse = (
                min(opened.adverse, candle.low)
                if opened.plan.direction.value == "LONG"
                else max(opened.adverse, candle.high)
            )
            damage_score = self._damage_score(
                opened, candle, observation, confirmed_swings
            )
            swing_kind = (
                SwingKind.LOW
                if opened.plan.direction is Direction.LONG
                else SwingKind.HIGH
            )
            swing_prices = tuple(
                swing.price for swing in confirmed_swings if swing.kind is swing_kind
            )
            opened.state = update_trail(
                opened.state,
                candle=candle,
                adr20=opened.adr20,
                ema20=None,
                confirmed_swing=swing_prices[-1] if swing_prices else None,
                prior_bar_extreme=opened.prior_bar_extreme,
                damage_score=damage_score,
            )
            opened.recent_closes.append(candle.close)
            opened.recent_closes[:] = opened.recent_closes[-3:]
            opened.prior_bar_extreme = (
                candle.low
                if opened.plan.direction is Direction.LONG
                else candle.high
            )
            opposing_trap = any(
                item.event.new_state is PatternState.TRAP_CONFIRMED
                and item.event.direction is not opened.plan.direction
                and item.confidence >= Decimal(75)
                for item in candidates
            )
            if opened.state.exit_queued:
                opened.queued_reason = "STRUCTURAL_DAMAGE"
                opened.signal_candle = candle
            elif opposing_trap:
                opened.queued_reason = "OPPOSING_TRAP"
                opened.signal_candle = candle
            elif opened.state.bars_held >= self.max_hold_bars:
                opened.queued_reason = "MAX_HOLD"
                opened.signal_candle = candle
        if decision.action not in {DecisionAction.LONG, DecisionAction.SHORT}:
            return (), ()
        if self.has_exposure(candle) or decision.entry_plan is None:
            return (), ()
        selected = next(
            (
                item
                for item in candidates
                if item.event.instance_id == decision.entry_plan.pattern_instance_id
            ),
            None,
        )
        if selected is None or selected.atr20 is None or selected.adr20 is None:
            return (), ()
        quantity = (self.risk_budget / decision.entry_plan.risk_per_unit).to_integral_value(
            rounding=ROUND_FLOOR
        )
        if quantity <= 0:
            return (), ()
        trade_id = deterministic_id(
            "trade", (self.run_id, decision.decision_id, decision.entry_plan.plan_id)
        )
        self._pending[key] = _Pending(
            trade_id,
            decision.entry_plan,
            selected.atr20,
            selected.adr20,
            quantity,
            selected.event.reference_level,
        )
        event = TradeEvent(
            trade_event_id=deterministic_id(
                "trade_event", (self.run_id, trade_id, decision.entry_plan.plan_id, "created")
            ),
            run_id=self.run_id,
            trade_id=trade_id,
            event_time=decision.known_at,
            event_type=TradeEventType.PLAN_CREATED,
            quantity=quantity,
            payload={
                "decision_id": decision.decision_id,
                "plan_id": decision.entry_plan.plan_id,
                "normalized_risk_budget_currency": self.risk_budget,
            },
        )
        return (event,), ()

    @staticmethod
    def _damage_score(
        opened: _Open,
        candle: Candle,
        observation: Observation | None,
        confirmed_swings: tuple[Swing, ...],
    ) -> Decimal:
        if observation is None:
            return Decimal(0)
        features = observation.features
        ema20 = features.get("ema20")
        slope = features.get("ema20_slope_adr")
        atr20 = features.get("atr20")
        clv = features.get("clv")
        rvol = features.get("rvol20")
        long = opened.plan.direction is Direction.LONG
        swing_kind = SwingKind.LOW if long else SwingKind.HIGH
        relevant = [swing.price for swing in confirmed_swings if swing.kind is swing_kind]
        swing_break = bool(relevant) and (
            candle.close < relevant[-1] - Decimal("0.10") * opened.adr20
            if long
            else candle.close > relevant[-1] + Decimal("0.10") * opened.adr20
        )
        level_loss = (
            candle.close < opened.reference_level - Decimal("0.10") * opened.adr20
            if long
            else candle.close > opened.reference_level + Decimal("0.10") * opened.adr20
        )
        ma_damage = False
        if isinstance(ema20, Decimal) and isinstance(slope, Decimal):
            ma_damage = (
                candle.close < ema20 and slope < 0
                if long
                else candle.close > ema20 and slope > 0
            )
        body = abs(candle.close - candle.open)
        impulse = False
        if all(isinstance(value, Decimal) for value in (atr20, clv, rvol)):
            atr = cast(Decimal, atr20)
            close_location = cast(Decimal, clv)
            relative_volume = cast(Decimal, rvol)
            impulse = (
                body >= Decimal("0.75") * atr
                and relative_volume >= Decimal("1.20")
                and (
                    close_location <= Decimal("0.25")
                    if long
                    else close_location >= Decimal("0.75")
                )
            )
        closes = (*opened.recent_closes, candle.close)[-3:]
        damaged_level = (
            opened.reference_level - Decimal("0.10") * opened.adr20
            if long
            else opened.reference_level + Decimal("0.10") * opened.adr20
        )
        follow_through = len(closes) == 3 and sum(
            close < damaged_level if long else close > damaged_level
            for close in closes
        ) >= 2
        return structural_damage(
            DamageInputs(swing_break, level_loss, ma_damage, impulse, follow_through)
        )

    def _complete(
        self,
        opened: _Open,
        candle: Candle,
        exit_price: Decimal,
        exit_cost: Decimal,
    ) -> CompletedTrade:
        return complete_trade(
            trade_id=opened.trade_id,
            run_id=self.run_id,
            symbol=opened.plan.symbol,
            timeframe=opened.plan.timeframe,
            direction=opened.plan.direction,
            entry_time=opened.entry_time,
            exit_time=candle.close_time,
            entry_price=opened.state.entry,
            exit_price=exit_price,
            initial_risk=opened.state.risk,
            favorable_extreme=opened.favorable,
            adverse_extreme=opened.adverse,
            hold_bars=opened.state.bars_held,
            # Fill prices already include adverse slippage; no extra commission model exists.
            total_cost=Decimal(0),
        )
