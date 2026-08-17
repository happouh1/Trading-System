"""Bullish/bearish reclaim acceptance and failure state machine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from trading_system.domain import Direction, Level, PatternEvent, PatternState
from trading_system.patterns.breaks import PatternBar
from trading_system.serialization import deterministic_id


@dataclass(slots=True)
class _Reclaim:
    instance_id: str
    direction: Direction
    level: Level
    state: PatternState
    candidate_index: int
    candidate_rvol: Decimal | None
    accepted_closes: int
    distance_sum: Decimal
    reclaim_velocity: Decimal
    parent_instance_id: str | None
    sequence_low: Decimal
    sequence_high: Decimal
    retest_extreme: Decimal | None = None


class ReclaimPatternMachine:
    pattern_version = "1.0.0"

    def __init__(self, run_id: str, config_hash: str, code_version: str) -> None:
        self.run_id = run_id
        self.config_hash = config_hash
        self.code_version = code_version
        self._bars: dict[str, list[PatternBar]] = {}
        self._instances: dict[tuple[str, str, Direction], _Reclaim] = {}

    def push(
        self,
        bar: PatternBar,
        levels: tuple[Level, ...],
        sweep_parents: dict[str, str] | None = None,
    ) -> tuple[PatternEvent, ...]:
        bars = self._bars.setdefault(bar.candle.symbol, [])
        if bars and bar.candle.close_time <= bars[-1].candle.close_time:
            raise ValueError("reclaim bars must be strictly increasing")
        bars.append(bar)
        index = len(bars) - 1
        parents = sweep_parents or {}
        events: list[PatternEvent] = []
        for level in sorted(levels, key=lambda item: item.level_id):
            if level.symbol != bar.candle.symbol or level.known_at >= bar.candle.close_time:
                continue
            for direction in (Direction.LONG, Direction.SHORT):
                key = (bar.candle.symbol, level.level_id, direction)
                instance = self._instances.get(key)
                if instance is None:
                    instance = self._candidate(
                        bars, bar, level, direction, index, parents.get(level.level_id)
                    )
                    if instance is not None:
                        self._instances[key] = instance
                        events.append(self._event(bar, instance, None, PatternState.CANDIDATE))
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
        index: int,
        parent_instance_id: str | None,
    ) -> _Reclaim | None:
        if len(bars) < 2:
            return None
        reference = level.lower_price if direction is Direction.LONG else level.upper_price
        prior = bars[max(0, len(bars) - 11) : -1]
        loss_indexes = [
            offset
            for offset, prior_bar in enumerate(prior)
            if (
                prior_bar.candle.close < reference - Decimal("0.05") * prior_bar.adr20
                if direction is Direction.LONG
                else prior_bar.candle.close > reference + Decimal("0.05") * prior_bar.adr20
            )
        ]
        if not loss_indexes:
            return None
        since_loss = [*prior[loss_indexes[-1] :], bar]
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
        body_fraction = body / max(candle_range, Decimal("1e-12"))
        if direction is Direction.LONG:
            extreme = min(item.candle.low for item in since_loss)
            distance = (bar.candle.close - reference) / bar.adr20
            displacement = (bar.candle.close - extreme) / bar.adr20
            matched = (
                bar.candle.close > reference + Decimal("0.05") * bar.adr20
                and clv >= Decimal("0.65")
                and body_fraction >= Decimal("0.45")
                and displacement >= Decimal("0.25")
            )
        else:
            extreme = max(item.candle.high for item in since_loss)
            distance = (reference - bar.candle.close) / bar.adr20
            displacement = (extreme - bar.candle.close) / bar.adr20
            matched = (
                bar.candle.close < reference - Decimal("0.05") * bar.adr20
                and clv <= Decimal("0.35")
                and body_fraction >= Decimal("0.45")
                and displacement >= Decimal("0.25")
            )
        if not matched:
            return None
        bars_since_extreme = max(len(since_loss) - 1, 1)
        identity = (self.run_id, level.level_id, direction, bar.candle.candle_id)
        return _Reclaim(
            instance_id=deterministic_id("reclaim_instance", identity),
            direction=direction,
            level=level,
            state=PatternState.CANDIDATE,
            candidate_index=index,
            candidate_rvol=rvol if isinstance(rvol, Decimal) else None,
            accepted_closes=1,
            distance_sum=distance,
            reclaim_velocity=displacement / Decimal(bars_since_extreme),
            parent_instance_id=parent_instance_id,
            sequence_low=min(item.candle.low for item in since_loss),
            sequence_high=max(item.candle.high for item in since_loss),
        )

    def _advance(
        self, bar: PatternBar, index: int, instance: _Reclaim
    ) -> PatternEvent | None:
        instance.sequence_low = min(instance.sequence_low, bar.candle.low)
        instance.sequence_high = max(instance.sequence_high, bar.candle.high)
        if bar.retest_held:
            instance.retest_extreme = (
                bar.candle.low
                if instance.direction is Direction.LONG
                else bar.candle.high
            )
        if instance.state not in (PatternState.CANDIDATE, PatternState.PENDING):
            return None
        age = index - instance.candidate_index
        distance = self._distance(bar, instance)
        if age <= 3 and distance <= Decimal("-0.10"):
            prior = instance.state
            instance.state = PatternState.FAILED
            return self._event(bar, instance, prior, PatternState.FAILED)
        if distance >= Decimal("0.05"):
            instance.accepted_closes += 1
            instance.distance_sum += distance
        if instance.accepted_closes >= 2:
            score = self._score(instance, bar.retest_held)
            volume_or_retest = (
                instance.candidate_rvol is not None
                and instance.candidate_rvol >= Decimal("1.20")
            ) or bar.retest_held
            if score >= Decimal(65) and volume_or_retest:
                prior = instance.state
                instance.state = PatternState.ACCEPTED
                return self._event(bar, instance, prior, PatternState.ACCEPTED, score)
        if age >= 3:
            prior = instance.state
            instance.state = PatternState.INVALIDATED
            return self._event(bar, instance, prior, PatternState.INVALIDATED)
        if instance.state is PatternState.CANDIDATE:
            instance.state = PatternState.PENDING
            return self._event(bar, instance, PatternState.CANDIDATE, PatternState.PENDING)
        return None

    @staticmethod
    def _distance(bar: PatternBar, instance: _Reclaim) -> Decimal:
        reference = (
            instance.level.lower_price
            if instance.direction is Direction.LONG
            else instance.level.upper_price
        )
        sign = Decimal(1) if instance.direction is Direction.LONG else Decimal(-1)
        return sign * (bar.candle.close - reference) / bar.adr20

    @staticmethod
    def _score(instance: _Reclaim, retest: bool) -> Decimal:
        persistence = Decimal(instance.accepted_closes) / Decimal(3)
        mean = instance.distance_sum / Decimal(instance.accepted_closes)
        distance = min(mean / Decimal("0.20"), Decimal(1))
        volume = Decimal(0)
        if instance.candidate_rvol is not None:
            volume = min(max(instance.candidate_rvol - Decimal(1), Decimal(0)), Decimal(1))
        result = Decimal(100) * (
            Decimal("0.35") * persistence
            + Decimal("0.25") * distance
            + Decimal("0.20") * volume
            + Decimal("0.20") * Decimal(int(retest))
        )
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    def _event(
        self,
        bar: PatternBar,
        instance: _Reclaim,
        prior: PatternState | None,
        new: PatternState,
        score: Decimal | None = None,
    ) -> PatternEvent:
        reasons = {
            PatternState.CANDIDATE: ("RECLAIM_CANDIDATE",),
            PatternState.PENDING: ("ACCEPTANCE_PENDING",),
            PatternState.ACCEPTED: ("RECLAIM_ACCEPTED",),
            PatternState.FAILED: ("RECLAIM_FAILED",),
            PatternState.INVALIDATED: ("ACCEPTANCE_EXPIRED",),
        }
        features: dict[str, object] = {
            "reclaim_velocity": instance.reclaim_velocity,
            "parent_instance_id": instance.parent_instance_id,
            "confirmation_score": score,
            "trigger_extreme": (
                bar.candle.low
                if instance.direction is Direction.LONG
                else bar.candle.high
            ),
            "sequence_extreme": (
                instance.sequence_low
                if instance.direction is Direction.LONG
                else instance.sequence_high
            ),
            "retest_extreme": instance.retest_extreme,
            "directional_runway_adr": (
                bar.long_runway_adr
                if instance.direction is Direction.LONG
                else bar.short_runway_adr
            ),
            "reference_level_confluence": instance.level.confluence_score,
        }
        if score is not None:
            features["acceptance_score"] = score
            velocity_score = min(
                max(instance.reclaim_velocity / Decimal("0.50"), Decimal(0)),
                Decimal(1),
            ) * Decimal(100)
            features["pattern_quality"] = (
                Decimal("0.50") * score
                + Decimal("0.30") * velocity_score
                + Decimal("0.20") * instance.level.confluence_score
            )
        else:
            features["pattern_quality"] = None
        return PatternEvent(
            event_id=deterministic_id(
                "pattern_event", (instance.instance_id, new, bar.candle.candle_id)
            ),
            run_id=self.run_id,
            observation_id=bar.observation.observation_id,
            symbol=bar.candle.symbol,
            timeframe=bar.candle.timeframe,
            known_at=bar.candle.close_time,
            pattern_family="RECLAIM",
            pattern_name=(
                "BULLISH_RECLAIM"
                if instance.direction is Direction.LONG
                else "BEARISH_RECLAIM"
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
            features=features,
            evidence_candle_ids=(bar.candle.candle_id,),
            reason_codes=reasons[new],
            config_hash=self.config_hash,
            code_version=self.code_version,
        )
