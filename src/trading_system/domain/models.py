"""Immutable Phase 0 domain contracts and their invariant checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import TypeVar

from trading_system.serialization import canonical_json, deterministic_id
from trading_system.versioning import SemanticVersion


class Timeframe(StrEnum):
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class SwingKind(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class LevelKind(StrEnum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    BASE_BOUNDARY = "BASE_BOUNDARY"
    PRIOR_HIGH = "PRIOR_HIGH"
    PRIOR_LOW = "PRIOR_LOW"
    BREAK_LEVEL = "BREAK_LEVEL"


class PatternState(StrEnum):
    INACTIVE = "INACTIVE"
    CANDIDATE = "CANDIDATE"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    ACTIVE = "ACTIVE"
    RETESTING = "RETESTING"
    CONTINUED = "CONTINUED"
    FAILED = "FAILED"
    TRAP_CONFIRMED = "TRAP_CONFIRMED"
    INVALIDATED = "INVALIDATED"


class DecisionAction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"


class TradeStyle(StrEnum):
    CONTINUATION = "CONTINUATION"
    COUNTERTREND = "COUNTERTREND"


class TradeEventType(StrEnum):
    PLAN_CREATED = "PLAN_CREATED"
    ENTRY_FILLED = "ENTRY_FILLED"
    STOP_UPDATED = "STOP_UPDATED"
    HOLD = "HOLD"
    EXIT_FILLED = "EXIT_FILLED"
    CANCELLED = "CANCELLED"


def _utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")


def _score(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < 0 or value > 100:
        raise ValueError(f"{name} must be between 0 and 100")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):
        raise TypeError("expected mapping")
    return frozen


@dataclass(frozen=True, slots=True)
class DomainModel:
    def to_json(self) -> str:
        return canonical_json(self)


@dataclass(frozen=True, slots=True)
class Candle(DomainModel):
    symbol: str
    timeframe: Timeframe
    open_time: datetime
    close_time: datetime
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_complete: bool
    adjustment_factor: Decimal
    source: str
    source_revision: str
    candle_id: str = ""
    raw_open: Decimal | None = None
    raw_high: Decimal | None = None
    raw_low: Decimal | None = None
    raw_close: Decimal | None = None
    raw_volume: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be nonempty uppercase text")
        _utc(self.open_time, "open_time")
        _utc(self.close_time, "close_time")
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        for name in ("open", "high", "low", "close", "adjustment_factor"):
            _positive(getattr(self, name), name)
        if self.volume < 0 or not self.volume.is_finite():
            raise ValueError("volume must be finite and nonnegative")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC invariants violated")
        if self.high < self.low:
            raise ValueError("high must be at least low")
        if not self.source or not self.source_revision:
            raise ValueError("source and source_revision are required")
        raw_prices = (self.raw_open, self.raw_high, self.raw_low, self.raw_close)
        if any(value is not None for value in raw_prices):
            if any(value is None for value in raw_prices):
                raise ValueError("raw OHLC fields must be provided together")
            for name in ("raw_open", "raw_high", "raw_low", "raw_close"):
                value = getattr(self, name)
                if value is not None:
                    _positive(value, name)
            assert self.raw_high is not None
            assert self.raw_low is not None
            assert self.raw_open is not None
            assert self.raw_close is not None
            if self.raw_high < max(self.raw_open, self.raw_close):
                raise ValueError("raw OHLC invariants violated")
            if self.raw_low > min(self.raw_open, self.raw_close):
                raise ValueError("raw OHLC invariants violated")
            adjusted_pairs = (
                (self.open, self.raw_open),
                (self.high, self.raw_high),
                (self.low, self.raw_low),
                (self.close, self.raw_close),
            )
            if any(adjusted != raw * self.adjustment_factor for adjusted, raw in adjusted_pairs):
                raise ValueError("adjusted OHLC must equal raw OHLC times adjustment_factor")
        if self.raw_volume is not None and (
            self.raw_volume < 0 or not self.raw_volume.is_finite()
        ):
            raise ValueError("raw_volume must be finite and nonnegative")
        if self.raw_volume is not None and self.volume != self.raw_volume:
            raise ValueError("Phase 1A volume must equal raw_volume")
        if not self.candle_id:
            identity = (self.symbol, self.timeframe, self.open_time, self.source_revision)
            object.__setattr__(self, "candle_id", deterministic_id("candle", identity))


@dataclass(frozen=True, slots=True)
class Swing(DomainModel):
    swing_id: str
    symbol: str
    timeframe: Timeframe
    kind: SwingKind
    price: Decimal
    pivot_time: datetime
    confirmed_at: datetime
    evidence_candle_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _positive(self.price, "price")
        _utc(self.pivot_time, "pivot_time")
        _utc(self.confirmed_at, "confirmed_at")
        if self.confirmed_at < self.pivot_time:
            raise ValueError("confirmed_at cannot precede pivot_time")
        if not self.evidence_candle_ids:
            raise ValueError("swing evidence is required")


@dataclass(frozen=True, slots=True)
class Level(DomainModel):
    level_id: str
    run_id: str
    symbol: str
    timeframe: Timeframe
    known_at: datetime
    lower_price: Decimal
    upper_price: Decimal
    kind: LevelKind
    confluence_score: Decimal
    evidence_candle_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _utc(self.known_at, "known_at")
        _positive(self.lower_price, "lower_price")
        _positive(self.upper_price, "upper_price")
        if self.lower_price > self.upper_price:
            raise ValueError("lower_price cannot exceed upper_price")
        _score(self.confluence_score, "confluence_score")


@dataclass(frozen=True, slots=True)
class PatternEvent(DomainModel):
    event_id: str
    run_id: str
    observation_id: str
    symbol: str
    timeframe: Timeframe
    known_at: datetime
    pattern_family: str
    pattern_name: str
    pattern_version: str
    instance_id: str
    prior_state: PatternState | None
    new_state: PatternState
    direction: Direction
    reference_level: Decimal | None
    features: Mapping[str, object] = field(default_factory=dict)
    evidence_candle_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    config_hash: str = ""
    code_version: str = ""

    def __post_init__(self) -> None:
        _utc(self.known_at, "known_at")
        SemanticVersion.parse(self.pattern_version)
        if self.reference_level is not None:
            _positive(self.reference_level, "reference_level")
        object.__setattr__(self, "features", _mapping(self.features))
        if not self.pattern_family or not self.pattern_name:
            raise ValueError("pattern family and name are required")


@dataclass(frozen=True, slots=True)
class RuleEvidence(DomainModel):
    rule_id: str
    actual: object
    operator: str
    threshold: object
    passed: bool


@dataclass(frozen=True, slots=True)
class TradePlan(DomainModel):
    plan_id: str
    symbol: str
    timeframe: Timeframe
    direction: Direction
    created_at: datetime
    planned_entry: Decimal
    initial_stop: Decimal
    risk_per_unit: Decimal
    runway_adr: Decimal
    reward_risk: Decimal
    pattern_instance_id: str

    def __post_init__(self) -> None:
        _utc(self.created_at, "created_at")
        for name in ("planned_entry", "initial_stop", "risk_per_unit"):
            _positive(getattr(self, name), name)
        if self.direction is Direction.LONG and self.initial_stop >= self.planned_entry:
            raise ValueError("long stop must be below entry")
        if self.direction is Direction.SHORT and self.initial_stop <= self.planned_entry:
            raise ValueError("short stop must be above entry")
        if self.direction is Direction.NONE:
            raise ValueError("trade plan direction cannot be NONE")
        if self.runway_adr < 0 or self.reward_risk < 0:
            raise ValueError("runway and reward/risk must be nonnegative")


@dataclass(frozen=True, slots=True)
class Decision(DomainModel):
    decision_id: str
    run_id: str
    observation_id: str
    known_at: datetime
    action: DecisionAction
    direction: Direction
    setup_quality: Decimal
    entry_quality: Decimal
    confidence: Decimal
    trade_style: TradeStyle | None
    entry_plan: TradePlan | None
    missing_conditions: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    timeframe_states: Mapping[str, str] = field(default_factory=dict)
    explanation: tuple[RuleEvidence, ...] = ()

    def __post_init__(self) -> None:
        _utc(self.known_at, "known_at")
        for name in ("setup_quality", "entry_quality", "confidence"):
            _score(getattr(self, name), name)
        object.__setattr__(self, "timeframe_states", _mapping(self.timeframe_states))
        directional = self.action in (DecisionAction.LONG, DecisionAction.SHORT)
        if directional and self.entry_plan is None:
            raise ValueError("LONG/SHORT decision requires entry_plan")
        if self.action is DecisionAction.NO_TRADE and not self.rejection_reasons:
            raise ValueError("NO_TRADE requires at least one rejection reason")


@dataclass(frozen=True, slots=True)
class TradeEvent(DomainModel):
    trade_event_id: str
    run_id: str
    trade_id: str
    event_time: datetime
    event_type: TradeEventType
    price: Decimal | None = None
    quantity: Decimal | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _utc(self.event_time, "event_time")
        if self.price is not None:
            _positive(self.price, "price")
        if self.quantity is not None:
            _positive(self.quantity, "quantity")
        object.__setattr__(self, "payload", _mapping(self.payload))


@dataclass(frozen=True, slots=True)
class Observation(DomainModel):
    observation_id: str
    run_id: str
    candle_id: str
    known_at: datetime
    schema_version: str
    input_fingerprint: str
    features: Mapping[str, object]
    data_quality: Mapping[str, object]

    def __post_init__(self) -> None:
        _utc(self.known_at, "known_at")
        SemanticVersion.parse(self.schema_version)
        object.__setattr__(self, "features", _mapping(self.features))
        object.__setattr__(self, "data_quality", _mapping(self.data_quality))


@dataclass(frozen=True, slots=True)
class Outcome(DomainModel):
    outcome_id: str
    run_id: str
    observation_id: str
    label_version: str
    horizon_bars: int
    label_available_at: datetime
    forward_return: Decimal | None = None
    mfe_r: Decimal | None = None
    mae_r: Decimal | None = None
    time_to_1r: int | None = None
    time_to_2r: int | None = None
    outcome_label: str | None = None

    def __post_init__(self) -> None:
        SemanticVersion.parse(self.label_version)
        _utc(self.label_available_at, "label_available_at")
        if self.horizon_bars <= 0:
            raise ValueError("horizon_bars must be positive")
        for name in ("forward_return", "mfe_r", "mae_r"):
            value = getattr(self, name)
            if value is not None and not value.is_finite():
                raise ValueError(f"{name} must be finite")
        if self.mfe_r is not None and self.mfe_r < 0:
            raise ValueError("mfe_r must be nonnegative")
        if self.mae_r is not None and self.mae_r < 0:
            raise ValueError("mae_r must be nonnegative")


ModelT = TypeVar("ModelT", bound=DomainModel)
