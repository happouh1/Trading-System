"""Causal bullish and bearish liquidity-sweep confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trading_system.domain import Direction, Level, PatternEvent, PatternState
from trading_system.patterns.breaks import PatternBar
from trading_system.patterns.quality import wick_quality
from trading_system.serialization import deterministic_id


@dataclass(slots=True)
class _Sweep:
    instance_id: str
    direction: Direction
    level: Level
    state: PatternState
    candidate_index: int
    midpoint: Decimal
    wick_quality: Decimal
    trigger_extreme: Decimal
    confirmation_bars: int = 0
    max_midpoint_displacement_adr: Decimal = Decimal(0)
    follow_through: bool = False


class SweepPatternMachine:
    pattern_version = "1.2.0"

    def __init__(self, run_id: str, config_hash: str, code_version: str) -> None:
        self.run_id = run_id
        self.config_hash = config_hash
        self.code_version = code_version
        self._bars: dict[str, list[PatternBar]] = {}
        self._instances: dict[tuple[str, str, Direction], _Sweep] = {}

    def push(self, bar: PatternBar, levels: tuple[Level, ...]) -> tuple[PatternEvent, ...]:
        bars = self._bars.setdefault(bar.candle.symbol, [])
        if bars and bar.candle.close_time <= bars[-1].candle.close_time:
            raise ValueError("sweep bars must be strictly increasing")
        bars.append(bar)
        index = len(bars) - 1
        events: list[PatternEvent] = []
        for level in sorted(levels, key=lambda item: item.level_id):
            if level.symbol != bar.candle.symbol or level.known_at >= bar.candle.close_time:
                continue
            for direction in (Direction.LONG, Direction.SHORT):
                key = (bar.candle.symbol, level.level_id, direction)
                instance = self._instances.get(key)
                if instance is None:
                    instance = self._candidate(bar, level, direction, index)
                    if instance is not None:
                        self._instances[key] = instance
                        events.append(self._event(bar, instance, None, PatternState.CANDIDATE))
                else:
                    event = self._advance(bar, index, instance)
                    if event is not None:
                        events.append(event)
        return tuple(events)

    def _candidate(
        self, bar: PatternBar, level: Level, direction: Direction, index: int
    ) -> _Sweep | None:
        candle = bar.candle
        features = bar.observation.features
        candle_range = features.get("range")
        clv = features.get("clv")
        lower_wick = features.get("lower_wick")
        upper_wick = features.get("upper_wick")
        wick_fraction: Decimal | None
        if not isinstance(candle_range, Decimal) or candle_range <= 0:
            return None
        if not isinstance(clv, Decimal):
            return None
        if direction is Direction.LONG:
            reference = level.lower_price
            penetration = (reference - candle.low) / bar.adr20
            matched = (
                candle.low < reference - Decimal("0.05") * bar.adr20
                and candle.close > reference
                and Decimal("0.05") <= penetration <= Decimal("0.50")
                and isinstance(lower_wick, Decimal)
                and lower_wick / candle_range >= Decimal("0.40")
                and clv >= Decimal("0.60")
            )
            wick_fraction = lower_wick / candle_range if isinstance(lower_wick, Decimal) else None
        else:
            reference = level.upper_price
            penetration = (candle.high - reference) / bar.adr20
            matched = (
                candle.high > reference + Decimal("0.05") * bar.adr20
                and candle.close < reference
                and Decimal("0.05") <= penetration <= Decimal("0.50")
                and isinstance(upper_wick, Decimal)
                and upper_wick / candle_range >= Decimal("0.40")
                and clv <= Decimal("0.40")
            )
            wick_fraction = upper_wick / candle_range if isinstance(upper_wick, Decimal) else None
        if not matched:
            return None
        assert isinstance(wick_fraction, Decimal)
        identity = (self.run_id, level.level_id, direction, candle.candle_id)
        return _Sweep(
            instance_id=deterministic_id("sweep_instance", identity),
            direction=direction,
            level=level,
            state=PatternState.CANDIDATE,
            candidate_index=index,
            midpoint=(candle.high + candle.low) / Decimal(2),
            wick_quality=wick_quality(wick_fraction),
            trigger_extreme=(candle.low if direction is Direction.LONG else candle.high),
        )

    def _advance(
        self, bar: PatternBar, index: int, instance: _Sweep
    ) -> PatternEvent | None:
        if instance.state not in (PatternState.CANDIDATE, PatternState.PENDING):
            return None
        age = index - instance.candidate_index
        reference = (
            instance.level.lower_price
            if instance.direction is Direction.LONG
            else instance.level.upper_price
        )
        closed_back = (
            bar.candle.close < reference
            if instance.direction is Direction.LONG
            else bar.candle.close > reference
        )
        if closed_back:
            prior = instance.state
            instance.state = PatternState.INVALIDATED
            return self._event(bar, instance, prior, PatternState.INVALIDATED)
        followed = (
            bar.candle.close > instance.midpoint
            if instance.direction is Direction.LONG
            else bar.candle.close < instance.midpoint
        )
        instance.confirmation_bars += 1
        signed_displacement = (
            bar.candle.close - instance.midpoint
            if instance.direction is Direction.LONG
            else instance.midpoint - bar.candle.close
        ) / bar.adr20
        instance.max_midpoint_displacement_adr = max(
            instance.max_midpoint_displacement_adr,
            signed_displacement,
            Decimal(0),
        )
        instance.follow_through = instance.follow_through or followed
        if age >= 2:
            prior = instance.state
            new = PatternState.ACCEPTED if instance.follow_through else PatternState.INVALIDATED
            instance.state = new
            return self._event(bar, instance, prior, new)
        if instance.state is PatternState.CANDIDATE:
            instance.state = PatternState.PENDING
            return self._event(bar, instance, PatternState.CANDIDATE, PatternState.PENDING)
        return None

    def _event(
        self,
        bar: PatternBar,
        instance: _Sweep,
        prior: PatternState | None,
        new: PatternState,
    ) -> PatternEvent:
        reasons = {
            PatternState.CANDIDATE: ("SWEEP_CANDIDATE",),
            PatternState.PENDING: ("REVERSAL_CONFIRMATION_PENDING",),
            PatternState.ACCEPTED: ("SWEEP_REVERSAL_CONFIRMED",),
            PatternState.INVALIDATED: ("SWEEP_INVALIDATED",),
        }
        confirmation_score = None
        pattern_quality = None
        if new is PatternState.ACCEPTED:
            persistence = Decimal(50) * Decimal(instance.confirmation_bars)
            midpoint = Decimal(100) * min(
                max(instance.max_midpoint_displacement_adr / Decimal("0.25"), Decimal(0)),
                Decimal(1),
            )
            confirmation_score = Decimal("0.60") * persistence + Decimal("0.40") * midpoint
            pattern_quality = (
                Decimal("0.50") * confirmation_score
                + Decimal("0.25") * instance.wick_quality
                + Decimal("0.25") * instance.level.confluence_score
            )
        return PatternEvent(
            event_id=deterministic_id(
                "pattern_event", (instance.instance_id, new, bar.candle.candle_id)
            ),
            run_id=self.run_id,
            observation_id=bar.observation.observation_id,
            symbol=bar.candle.symbol,
            timeframe=bar.candle.timeframe,
            known_at=bar.candle.close_time,
            pattern_family="LIQUIDITY_SWEEP",
            pattern_name=(
                "BULLISH_LIQUIDITY_SWEEP"
                if instance.direction is Direction.LONG
                else "BEARISH_LIQUIDITY_SWEEP"
            ),
            pattern_version=self.pattern_version,
            instance_id=instance.instance_id,
            prior_state=prior,
            new_state=new,
            direction=instance.direction,
            reference_level=(
                instance.level.lower_price
                if instance.direction is Direction.LONG
                else instance.level.upper_price
            ),
            features={
                "candidate_midpoint": instance.midpoint,
                "wick_quality": instance.wick_quality,
                "pattern_quality": pattern_quality,
                "confirmation_score": confirmation_score,
                "reversal_confirmation_score": confirmation_score,
                "trigger_extreme": (
                    instance.trigger_extreme
                ),
                "sequence_extreme": (
                    instance.trigger_extreme
                ),
                "retest_extreme": None,
                "directional_runway_adr": (
                    bar.long_runway_adr
                    if instance.direction is Direction.LONG
                    else bar.short_runway_adr
                ),
                "reference_level_confluence": instance.level.confluence_score,
            },
            evidence_candle_ids=(bar.candle.candle_id,),
            reason_codes=reasons[new],
            config_hash=self.config_hash,
            code_version=self.code_version,
        )
