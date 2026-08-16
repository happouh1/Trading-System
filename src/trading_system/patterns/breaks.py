"""Breakout/breakdown acceptance, failure, and trap state machine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

from trading_system.domain import (
    Candle,
    Direction,
    Level,
    Observation,
    PatternEvent,
    PatternState,
)
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class PatternBar:
    candle: Candle
    observation: Observation
    adr20: Decimal
    runway_adr: Decimal | None
    retest_held: bool = False

    def __post_init__(self) -> None:
        if self.candle.candle_id != self.observation.candle_id:
            raise ValueError("observation must describe the supplied candle")
        if self.observation.known_at != self.candle.close_time:
            raise ValueError("observation known_at must equal candle close")
        if self.adr20 <= 0 or not self.adr20.is_finite():
            raise ValueError("ADR20 must be finite and positive")


@dataclass(slots=True)
class _Instance:
    instance_id: str
    direction: Direction
    level: Level
    state: PatternState
    candidate_index: int
    candidate_rvol: Decimal | None
    maximum_excursion: Decimal
    accepted_closes: int = 0
    positive_distance_sum: Decimal = Decimal(0)
    failure_extreme: Decimal | None = None
    failure_clv_confirmed: bool = False


class BreakPatternMachine:
    """One transition per instance per completed bar, with causal evidence only."""

    pattern_version = "1.0.0"

    def __init__(self, run_id: str, config_hash: str, code_version: str) -> None:
        self.run_id = run_id
        self.config_hash = config_hash
        self.code_version = code_version
        self._bars: dict[str, list[PatternBar]] = {}
        self._instances: dict[tuple[str, str, Direction], _Instance] = {}

    def push(self, bar: PatternBar, levels: tuple[Level, ...]) -> tuple[PatternEvent, ...]:
        symbol_bars = self._bars.setdefault(bar.candle.symbol, [])
        if symbol_bars and bar.candle.close_time <= symbol_bars[-1].candle.close_time:
            raise ValueError("pattern bars must be strictly increasing")
        symbol_bars.append(bar)
        index = len(symbol_bars) - 1
        events: list[PatternEvent] = []
        for level in sorted(levels, key=lambda item: item.level_id):
            if level.symbol != bar.candle.symbol:
                continue
            if level.known_at >= bar.candle.close_time:
                continue
            for direction in (Direction.LONG, Direction.SHORT):
                key = (bar.candle.symbol, level.level_id, direction)
                instance = self._instances.get(key)
                if instance is None:
                    candidate = self._candidate(symbol_bars, bar, level, direction)
                    if candidate is not None:
                        self._instances[key] = candidate
                        events.append(
                            self._event(
                                bar,
                                candidate,
                                None,
                                PatternState.CANDIDATE,
                                ("BREAK_CANDIDATE",),
                            )
                        )
                else:
                    event = self._advance(bar, index, instance)
                    if event is not None:
                        events.append(event)
        return tuple(events)

    def _candidate(
        self,
        bars: list[PatternBar],
        bar: PatternBar,
        level: Level,
        direction: Direction,
    ) -> _Instance | None:
        if len(bars) < 2:
            return None
        previous = bars[-2].candle.close
        candle = bar.candle
        features = bar.observation.features
        clv = features.get("clv")
        body = features.get("body")
        candle_range = features.get("range")
        rvol = features.get("rvol20")
        if not all(isinstance(value, Decimal) for value in (clv, body, candle_range)):
            return None
        assert isinstance(clv, Decimal)
        assert isinstance(body, Decimal)
        assert isinstance(candle_range, Decimal)
        rvol_value = rvol if isinstance(rvol, Decimal) else None
        body_fraction = body / max(candle_range, Decimal("1e-12"))
        if direction is Direction.LONG:
            reference = level.upper_price
            matched = (
                previous <= reference + Decimal("0.05") * bar.adr20
                and candle.close > reference + Decimal("0.10") * bar.adr20
                and clv >= Decimal("0.70")
                and body_fraction >= Decimal("0.55")
                and (rvol_value is None or rvol_value >= Decimal("1.20"))
            )
            excursion = max(candle.high - reference, Decimal(0)) / bar.adr20
        else:
            reference = level.lower_price
            matched = (
                previous >= reference - Decimal("0.05") * bar.adr20
                and candle.close < reference - Decimal("0.10") * bar.adr20
                and clv <= Decimal("0.30")
                and body_fraction >= Decimal("0.55")
                and (rvol_value is None or rvol_value >= Decimal("1.20"))
            )
            excursion = max(reference - candle.low, Decimal(0)) / bar.adr20
        if not matched:
            return None
        identity = (self.run_id, level.level_id, direction, candle.candle_id)
        signed_close_distance = (
            (candle.close - reference) / bar.adr20
            if direction is Direction.LONG
            else (reference - candle.close) / bar.adr20
        )
        return _Instance(
            instance_id=deterministic_id("pattern_instance", identity),
            direction=direction,
            level=level,
            state=PatternState.CANDIDATE,
            candidate_index=len(bars) - 1,
            candidate_rvol=rvol_value,
            maximum_excursion=excursion,
            accepted_closes=1,
            positive_distance_sum=signed_close_distance,
        )

    def _advance(
        self, bar: PatternBar, index: int, instance: _Instance
    ) -> PatternEvent | None:
        if instance.state is PatternState.FAILED:
            return self._confirm_trap(bar, instance)
        if instance.state not in (PatternState.CANDIDATE, PatternState.PENDING):
            return None
        age = index - instance.candidate_index
        signed = self._signed_distance(bar, instance)
        if (
            age <= 3
            and signed <= Decimal("-0.10")
            and instance.maximum_excursion >= Decimal("0.10")
        ):
            prior = instance.state
            instance.state = PatternState.FAILED
            instance.failure_extreme = (
                bar.candle.low if instance.direction is Direction.LONG else bar.candle.high
            )
            clv = bar.observation.features.get("clv")
            instance.failure_clv_confirmed = isinstance(clv, Decimal) and (
                clv <= Decimal("0.35")
                if instance.direction is Direction.LONG
                else clv >= Decimal("0.65")
            )
            return self._event(bar, instance, prior, PatternState.FAILED, ("BREAK_FAILED",))
        if signed >= Decimal("0.05"):
            instance.accepted_closes += 1
            instance.positive_distance_sum += signed
        if instance.direction is Direction.LONG:
            excursion = max(bar.candle.high - instance.level.upper_price, Decimal(0)) / bar.adr20
        else:
            excursion = max(instance.level.lower_price - bar.candle.low, Decimal(0)) / bar.adr20
        instance.maximum_excursion = max(instance.maximum_excursion, excursion)
        if instance.accepted_closes >= 2:
            score = self._acceptance_score(instance, bar.retest_held)
            volume_or_retest = (
                instance.candidate_rvol is not None
                and instance.candidate_rvol >= Decimal("1.20")
            ) or bar.retest_held
            mean_distance = instance.positive_distance_sum / Decimal(instance.accepted_closes)
            if score >= Decimal(65) and mean_distance >= Decimal("0.05") and volume_or_retest:
                prior = instance.state
                instance.state = PatternState.ACCEPTED
                return self._event(
                    bar, instance, prior, PatternState.ACCEPTED, ("ACCEPTANCE_2_OF_3",), score
                )
        if age >= 3:
            prior = instance.state
            instance.state = PatternState.INVALIDATED
            return self._event(
                bar, instance, prior, PatternState.INVALIDATED, ("ACCEPTANCE_EXPIRED",)
            )
        if instance.state is PatternState.CANDIDATE:
            instance.state = PatternState.PENDING
            return self._event(
                bar,
                instance,
                PatternState.CANDIDATE,
                PatternState.PENDING,
                ("ACCEPTANCE_PENDING",),
            )
        return None

    def _confirm_trap(self, bar: PatternBar, instance: _Instance) -> PatternEvent | None:
        if bar.runway_adr is None or bar.runway_adr < Decimal("0.75"):
            return None
        if self._signed_distance(bar, instance) >= Decimal("0.05"):
            return None
        attracted = (
            instance.candidate_rvol is not None
            and instance.candidate_rvol >= Decimal("1.20")
        ) or instance.maximum_excursion >= Decimal("0.25")
        if instance.failure_extreme is None:
            return None
        follow_through = (
            bar.candle.low < instance.failure_extreme
            if instance.direction is Direction.LONG
            else bar.candle.high > instance.failure_extreme
        )
        if not attracted or not (instance.failure_clv_confirmed or follow_through):
            return None
        instance.state = PatternState.TRAP_CONFIRMED
        return self._event(
            bar, instance, PatternState.FAILED, PatternState.TRAP_CONFIRMED, ("TRAP_CONFIRMED",)
        )

    @staticmethod
    def _signed_distance(bar: PatternBar, instance: _Instance) -> Decimal:
        reference = (
            instance.level.upper_price
            if instance.direction is Direction.LONG
            else instance.level.lower_price
        )
        sign = Decimal(1) if instance.direction is Direction.LONG else Decimal(-1)
        return sign * (bar.candle.close - reference) / bar.adr20

    @staticmethod
    def _acceptance_score(instance: _Instance, retest: bool) -> Decimal:
        persistence = Decimal(instance.accepted_closes) / Decimal(3)
        mean = instance.positive_distance_sum / Decimal(instance.accepted_closes)
        distance = min(mean / Decimal("0.20"), Decimal(1))
        volume = Decimal(0)
        if instance.candidate_rvol is not None:
            volume = min(max(instance.candidate_rvol - Decimal(1), Decimal(0)), Decimal(1))
        score = Decimal(100) * (
            Decimal("0.35") * persistence
            + Decimal("0.25") * distance
            + Decimal("0.20") * volume
            + Decimal("0.20") * Decimal(int(retest))
        )
        return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    def _event(
        self,
        bar: PatternBar,
        instance: _Instance,
        prior: PatternState | None,
        new: PatternState,
        reasons: tuple[str, ...],
        acceptance_score: Decimal | None = None,
    ) -> PatternEvent:
        family = "BREAKOUT" if instance.direction is Direction.LONG else "BREAKDOWN"
        features: dict[str, object] = {"volume_unconfirmed": instance.candidate_rvol is None}
        if acceptance_score is not None:
            features["acceptance_score"] = acceptance_score
        event_id = deterministic_id(
            "pattern_event", (instance.instance_id, new, bar.candle.candle_id)
        )
        return PatternEvent(
            event_id=event_id,
            run_id=self.run_id,
            observation_id=bar.observation.observation_id,
            symbol=bar.candle.symbol,
            timeframe=bar.candle.timeframe,
            known_at=bar.candle.close_time,
            pattern_family=family,
            pattern_name=f"BASE_{family}",
            pattern_version=self.pattern_version,
            instance_id=instance.instance_id,
            prior_state=prior,
            new_state=new,
            direction=instance.direction,
            reference_level=(
                instance.level.upper_price
                if instance.direction is Direction.LONG
                else instance.level.lower_price
            ),
            features=features,
            evidence_candle_ids=(bar.candle.candle_id,),
            reason_codes=reasons,
            config_hash=self.config_hash,
            code_version=self.code_version,
        )
