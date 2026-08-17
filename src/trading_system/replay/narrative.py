"""Causal structure, level, and pattern narrative integration."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from trading_system.decisions import DecisionCandidate, DecisionEngine, map_pattern_candidate
from trading_system.domain import (
    Candle,
    Decision,
    Direction,
    Level,
    LevelKind,
    Observation,
    PatternEvent,
    SwingKind,
    Timeframe,
)
from trading_system.features import CausalFeatureEngine
from trading_system.levels import LevelEngine, LevelSource, runway_adr
from trading_system.patterns import (
    BreakPatternMachine,
    PatternBar,
    ReclaimPatternMachine,
    SweepPatternMachine,
)
from trading_system.scoring import TimeframeState, asof_join
from trading_system.structure import StructureEngine, StructureSnapshot


@dataclass(frozen=True, slots=True)
class NarrativeResult:
    observation: Observation
    levels: tuple[Level, ...]
    pattern_events: tuple[PatternEvent, ...]
    candidates: tuple[DecisionCandidate, ...]
    decision: Decision
    structure: StructureSnapshot


class CausalNarrativePipeline:
    """Connect only fully specified causal engines; unresolved scoring remains NO_TRADE."""

    def __init__(self, run_id: str, config_hash: str, code_version: str) -> None:
        self.run_id = run_id
        self.features = CausalFeatureEngine(run_id)
        self.structure = StructureEngine()
        self.level_engine = LevelEngine()
        self.decisions = DecisionEngine(run_id)
        self._sources: dict[str, list[LevelSource]] = defaultdict(list)
        self._states: dict[str, list[TimeframeState]] = defaultdict(list)
        self._session_opens: dict[tuple[str, date], Decimal] = {}
        self._breaks = {
            timeframe: BreakPatternMachine(run_id, config_hash, code_version)
            for timeframe in (Timeframe.HOUR_1, Timeframe.HOUR_4)
        }
        self._reclaims = {
            timeframe: ReclaimPatternMachine(run_id, config_hash, code_version)
            for timeframe in (Timeframe.HOUR_1, Timeframe.HOUR_4)
        }
        self._sweeps = {
            timeframe: SweepPatternMachine(run_id, config_hash, code_version)
            for timeframe in (Timeframe.HOUR_1, Timeframe.HOUR_4)
        }

    def push(self, candle: Candle, *, position_already_open: bool = False) -> NarrativeResult:
        session_key = (candle.symbol, candle.session_date)
        self._session_opens.setdefault(session_key, candle.open)
        observation = self.features.push(candle)
        adr_value = observation.features.get("adr20")
        adr20 = adr_value if isinstance(adr_value, Decimal) else None
        snapshot = self.structure.push(candle, adr20)
        self._states[candle.symbol].append(
            TimeframeState(candle.timeframe, candle.close_time, candle.candle_id, snapshot.state)
        )
        for swing in snapshot.new_swings:
            self._sources[candle.symbol].append(
                LevelSource(
                    source_id=swing.swing_id,
                    symbol=swing.symbol,
                    timeframe=swing.timeframe,
                    known_at=swing.confirmed_at,
                    price=swing.price,
                    kind=(
                        LevelKind.SWING_HIGH
                        if swing.kind is SwingKind.HIGH
                        else LevelKind.SWING_LOW
                    ),
                    evidence_candle_ids=swing.evidence_candle_ids,
                )
            )
        levels = (
            self.level_engine.build(self.run_id, self._sources[candle.symbol], adr20)
            if adr20 is not None
            else ()
        )
        events: tuple[PatternEvent, ...] = ()
        if adr20 is not None and candle.timeframe in self._breaks:
            long_runway = runway_adr(candle.close, Direction.LONG, levels, adr20)
            short_runway = runway_adr(candle.close, Direction.SHORT, levels, adr20)
            bar = PatternBar(candle, observation, adr20, long_runway, short_runway)
            events = (
                *self._breaks[candle.timeframe].push(bar, levels),
                *self._sweeps[candle.timeframe].push(bar, levels),
                *self._reclaims[candle.timeframe].push(bar, levels),
            )
        mtf = asof_join(observation.known_at, self._states[candle.symbol])
        candidates = tuple(
            candidate
            for event in events
            if (
                candidate := map_pattern_candidate(
                    event=event,
                    candle=candle,
                    observation=observation,
                    structure=snapshot.state,
                    mtf=mtf,
                    levels=levels,
                    session_open=self._session_opens[session_key],
                    position_already_open=position_already_open,
                )
            )
            is not None
        )
        decision = self.decisions.decide(
            observation.observation_id,
            observation.known_at,
            candidates,
            tuple(
                (state.timeframe.value, state.state.value)
                for state in mtf.states
            ),
        )
        return NarrativeResult(observation, levels, events, candidates, decision, snapshot)
