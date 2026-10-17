"""Causal, research-only Stage A trend and breakout classification."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from trading_system.serialization import canonical_hash, deterministic_id

EASTERN = ZoneInfo("America/New_York")


class StageAConfigError(ValueError):
    """Raised when the immutable Stage A configuration is invalid."""


class StageAState(StrEnum):
    NOT_QUALIFIED = "NOT_QUALIFIED"
    QUALIFIED = "QUALIFIED"
    EXTENDED_WATCH = "EXTENDED_WATCH"
    OVEREXTENDED = "OVEREXTENDED"


class StageAVolumeBand(StrEnum):
    ORDINARY = "ORDINARY"
    SUPPORTING = "SUPPORTING"
    EXCEPTIONAL = "EXCEPTIONAL"


class StageATimeBucket(StrEnum):
    BEFORE_1000_ET = "BEFORE_1000_ET"
    FROM_1000_TO_1059_ET = "FROM_1000_TO_1059_ET"
    FROM_1100_TO_1159_ET = "FROM_1100_TO_1159_ET"
    AFTER_1200_ET = "AFTER_1200_ET"


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise StageAConfigError(f"{path} must be numeric")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise StageAConfigError(f"{path} must be numeric") from exc
    if not result.is_finite():
        raise StageAConfigError(f"{path} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class StageAConfig:
    values: Mapping[str, object]
    config_hash: str

    def section(self, name: str) -> Mapping[str, object]:
        value = self.values.get(name)
        if not isinstance(value, Mapping):
            raise StageAConfigError(f"{name} must be an object")
        return value

    def decimal(self, section: str, key: str) -> Decimal:
        return _decimal(self.section(section).get(key), f"{section}.{key}")


def load_stage_a_config(path: str | Path) -> StageAConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "stage_a_version",
        "setup",
        "entry_quality",
        "evaluation",
        "authority",
    }:
        raise StageAConfigError("Stage A config top-level keys are invalid")
    if raw["stage_a_version"] != "1.0.0":
        raise StageAConfigError("stage_a_version must be 1.0.0")
    setup = raw["setup"]
    if not isinstance(setup, dict) or set(setup) != {
        "minimum_price",
        "minimum_adr20_pct",
        "minimum_recent_volume_surge",
        "minimum_off_20d_high_pct",
    }:
        raise StageAConfigError("Stage A setup configuration is invalid")
    entry = raw["entry_quality"]
    if not isinstance(entry, dict) or set(entry) != {
        "extended_watch_vs_ema8_pct",
        "maximum_vs_ema8_pct",
        "gap_chase_warning_pct",
        "supporting_volume_surge",
        "exceptional_volume_surge",
    }:
        raise StageAConfigError("Stage A entry-quality configuration is invalid")
    for section, values in (
        ("setup", setup),
        ("entry_quality", entry),
    ):
        for key, value in values.items():
            _decimal(value, f"{section}.{key}")
    extended = _decimal(entry["extended_watch_vs_ema8_pct"], "entry_quality.extended")
    maximum = _decimal(entry["maximum_vs_ema8_pct"], "entry_quality.maximum")
    supporting = _decimal(entry["supporting_volume_surge"], "entry_quality.supporting")
    exceptional = _decimal(entry["exceptional_volume_surge"], "entry_quality.exceptional")
    minimum_volume = _decimal(setup["minimum_recent_volume_surge"], "setup.minimum_volume")
    if not (Decimal(0) <= extended < maximum):
        raise StageAConfigError("Stage A extension thresholds must increase")
    if not (minimum_volume <= supporting < exceptional):
        raise StageAConfigError("Stage A volume bands must increase")
    evaluation = raw["evaluation"]
    if evaluation != {
        "forward_sessions": 8,
        "dedupe_scope": "SYMBOL_SESSION",
        "record_mfe": True,
        "record_mae": True,
        "record_time_to_peak": True,
    }:
        raise StageAConfigError("Stage A evaluation contract is invalid")
    if raw["authority"] != {
        "research_only": True,
        "decision_authority": False,
        "broker_writes_enabled": False,
        "automatic_promotion_enabled": False,
    }:
        raise StageAConfigError("Stage A authority must remain research-only")
    return StageAConfig(MappingProxyType(dict(raw)), canonical_hash(raw))


@dataclass(frozen=True, slots=True)
class StageAObservation:
    symbol: str
    session_date: date
    known_at: datetime
    close: Decimal
    ema8: Decimal
    ema21: Decimal
    ema50: Decimal
    recent_volume_surge: Decimal
    off_20d_high_pct: Decimal
    adr20_pct: Decimal
    gap_pct: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Stage A symbol must be nonempty uppercase text")
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("Stage A known_at must be timezone-aware")
        if self.known_at.astimezone(EASTERN).date() != self.session_date:
            raise ValueError("Stage A known_at and session_date must identify the same ET day")
        numeric = (
            self.close,
            self.ema8,
            self.ema21,
            self.ema50,
            self.recent_volume_surge,
            self.off_20d_high_pct,
            self.adr20_pct,
        )
        if any(not value.is_finite() for value in numeric):
            raise ValueError("Stage A inputs must be finite")
        if min(self.close, self.ema8, self.ema21, self.ema50) <= 0:
            raise ValueError("Stage A prices and averages must be positive")
        if self.recent_volume_surge < 0 or self.adr20_pct < 0:
            raise ValueError("Stage A volume surge and ADR must be nonnegative")
        if self.gap_pct is not None and not self.gap_pct.is_finite():
            raise ValueError("Stage A gap must be finite when supplied")

    @property
    def vs_ema8_pct(self) -> Decimal:
        return (self.close - self.ema8) / self.ema8 * Decimal(100)


@dataclass(frozen=True, slots=True)
class StageAAssessment:
    assessment_id: str
    observation_id: str
    config_hash: str
    state: StageAState
    setup_qualified: bool
    entry_eligible: bool
    vs_ema8_pct: Decimal
    volume_band: StageAVolumeBand
    time_bucket: StageATimeBucket
    gap_chase_warning: bool
    reason_codes: tuple[str, ...]
    research_only: bool = True
    broker_write_performed: bool = False


def _time_bucket(known_at: datetime) -> StageATimeBucket:
    local = known_at.astimezone(EASTERN).time()
    if local < time(10):
        return StageATimeBucket.BEFORE_1000_ET
    if local < time(11):
        return StageATimeBucket.FROM_1000_TO_1059_ET
    if local < time(12):
        return StageATimeBucket.FROM_1100_TO_1159_ET
    return StageATimeBucket.AFTER_1200_ET


def assess_stage_a(observation: StageAObservation, config: StageAConfig) -> StageAAssessment:
    """Classify a causal observation without creating decision or execution authority."""
    setup = config.section("setup")
    entry = config.section("entry_quality")
    reasons: list[str] = []
    if observation.close < _decimal(setup["minimum_price"], "setup.minimum_price"):
        reasons.append("STAGE_A_PRICE_BELOW_MINIMUM")
    if observation.adr20_pct < _decimal(setup["minimum_adr20_pct"], "setup.minimum_adr20_pct"):
        reasons.append("STAGE_A_ADR_BELOW_MINIMUM")
    if observation.recent_volume_surge < _decimal(
        setup["minimum_recent_volume_surge"], "setup.minimum_recent_volume_surge"
    ):
        reasons.append("STAGE_A_VOLUME_SURGE_MISSING")
    if observation.off_20d_high_pct <= _decimal(
        setup["minimum_off_20d_high_pct"], "setup.minimum_off_20d_high_pct"
    ):
        reasons.append("STAGE_A_TOO_FAR_FROM_20D_HIGH")
    if not (observation.close > observation.ema8 > observation.ema21 > observation.ema50):
        reasons.append("STAGE_A_FULL_BULL_STACK_MISSING")

    supporting = _decimal(entry["supporting_volume_surge"], "entry.supporting_volume")
    exceptional = _decimal(entry["exceptional_volume_surge"], "entry.exceptional_volume")
    if observation.recent_volume_surge >= exceptional:
        volume_band = StageAVolumeBand.EXCEPTIONAL
    elif observation.recent_volume_surge >= supporting:
        volume_band = StageAVolumeBand.SUPPORTING
    else:
        volume_band = StageAVolumeBand.ORDINARY

    setup_qualified = not reasons
    if not setup_qualified:
        state = StageAState.NOT_QUALIFIED
    elif observation.vs_ema8_pct > _decimal(entry["maximum_vs_ema8_pct"], "entry.maximum"):
        state = StageAState.OVEREXTENDED
        reasons.append("STAGE_A_OVEREXTENDED_ABOVE_EMA8")
    elif observation.vs_ema8_pct >= _decimal(
        entry["extended_watch_vs_ema8_pct"], "entry.extended_watch"
    ):
        state = StageAState.EXTENDED_WATCH
        reasons.append("STAGE_A_EXTENSION_WARNING")
    else:
        state = StageAState.QUALIFIED

    gap_warning = observation.gap_pct is not None and observation.gap_pct >= _decimal(
        entry["gap_chase_warning_pct"], "entry.gap_chase_warning"
    )
    if gap_warning:
        reasons.append("STAGE_A_GAP_CHASE_WARNING")
    observation_identity = (
        config.values["stage_a_version"],
        observation.symbol,
        observation.session_date,
    )
    observation_id = deterministic_id("trend_stage_a_observation", observation_identity)
    ordered_reasons = tuple(sorted(reasons))
    assessment_identity = (
        observation_id,
        config.config_hash,
        state,
        volume_band,
        _time_bucket(observation.known_at),
        gap_warning,
        ordered_reasons,
    )
    return StageAAssessment(
        deterministic_id("trend_stage_a_assessment", assessment_identity),
        observation_id,
        config.config_hash,
        state,
        setup_qualified,
        state is StageAState.QUALIFIED and not gap_warning,
        observation.vs_ema8_pct,
        volume_band,
        _time_bucket(observation.known_at),
        gap_warning,
        ordered_reasons,
    )
