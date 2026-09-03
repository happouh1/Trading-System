"""Causal research contracts and detection for range-reclaim boxes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Timeframe
from trading_system.patterns.bases import BaseBar, BaseCandidate, BaseDetector
from trading_system.patterns.range_config import RangeReclaimConfig
from trading_system.serialization import deterministic_id


class RangeBoundary(StrEnum):
    LOWER = "LOWER"
    UPPER = "UPPER"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _positive(value: Decimal, name: str) -> None:
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class VolumePointOfControl:
    """Observed volume-at-price POC; never inferred from aggregate OHLCV."""

    price: Decimal
    known_at: datetime
    source_revision: str
    method_version: str

    def __post_init__(self) -> None:
        _positive(self.price, "price")
        _aware(self.known_at, "known_at")
        if not self.source_revision or not self.method_version:
            raise ValueError("source_revision and method_version are required")


@dataclass(frozen=True, slots=True)
class BoundaryEpisode:
    boundary: RangeBoundary
    candle_ids: tuple[str, ...]
    known_at: datetime

    def __post_init__(self) -> None:
        if not self.candle_ids or any(not item for item in self.candle_ids):
            raise ValueError("a boundary episode requires candle evidence")
        _aware(self.known_at, "known_at")


@dataclass(frozen=True, slots=True)
class RangeBox:
    box_id: str
    base_instance_id: str
    symbol: str
    timeframe: Timeframe
    start_candle_id: str
    end_candle_id: str
    start_time: datetime
    end_time: datetime
    known_at: datetime
    lower: Decimal
    upper: Decimal
    geometric_midpoint: Decimal
    volume_poc: VolumePointOfControl | None
    episodes: tuple[BoundaryEpisode, ...]
    lower_episode_count: int
    upper_episode_count: int
    width_adr: Decimal
    net_drift_adr: Decimal
    overlap_score: Decimal
    atr_compression: Decimal
    quality: Decimal
    parent_box_id: str | None
    config_hash: str
    code_version: str
    strategy_family: str = "RANGE_RECLAIM_CONTINUATION_V1"
    pattern_version: str = "7A.1.0"

    def __post_init__(self) -> None:
        if not self.box_id or not self.base_instance_id or not self.symbol:
            raise ValueError("box identity and symbol are required")
        if not self.start_candle_id or not self.end_candle_id:
            raise ValueError("box candle identities are required")
        for name in ("start_time", "end_time", "known_at"):
            _aware(getattr(self, name), name)
        if self.end_time <= self.start_time or self.known_at < self.end_time:
            raise ValueError("range-box times are inconsistent")
        _positive(self.lower, "lower")
        _positive(self.upper, "upper")
        if self.upper <= self.lower:
            raise ValueError("upper must exceed lower")
        if self.geometric_midpoint != (self.lower + self.upper) / Decimal(2):
            raise ValueError("geometric_midpoint must be the arithmetic range midpoint")
        if self.volume_poc is not None:
            if not self.lower <= self.volume_poc.price <= self.upper:
                raise ValueError("volume POC must lie inside the range")
            if self.volume_poc.known_at > self.known_at:
                raise ValueError("volume POC was not known when the box was known")
        if self.lower_episode_count != sum(
            item.boundary is RangeBoundary.LOWER for item in self.episodes
        ):
            raise ValueError("lower episode count does not match evidence")
        if self.upper_episode_count != sum(
            item.boundary is RangeBoundary.UPPER for item in self.episodes
        ):
            raise ValueError("upper episode count does not match evidence")
        previous_episode_time: datetime | None = None
        for episode in self.episodes:
            if episode.known_at > self.known_at:
                raise ValueError("boundary episode was not known when the box was known")
            if previous_episode_time is not None and episode.known_at <= previous_episode_time:
                raise ValueError("boundary episodes must be strictly chronological")
            previous_episode_time = episode.known_at
        for name in (
            "width_adr",
            "net_drift_adr",
            "overlap_score",
            "atr_compression",
            "quality",
        ):
            value = getattr(self, name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if not self.config_hash or not self.code_version:
            raise ValueError("config_hash and code_version are required")
        if self.strategy_family != "RANGE_RECLAIM_CONTINUATION_V1":
            raise ValueError("strategy_family is fixed for Phase 7A")
        if self.pattern_version != "7A.1.0":
            raise ValueError("pattern_version is fixed for Phase 7A")


class RangeBoxDetector:
    """Adapt the approved base detector with stricter rotation evidence."""

    def __init__(self, config: RangeReclaimConfig, *, code_version: str) -> None:
        if not code_version:
            raise ValueError("code_version is required")
        self.config = config
        self.code_version = code_version
        self.base_detector = BaseDetector(
            min_bars=config.min_bars,
            max_bars=config.max_bars,
        )

    def detect(
        self,
        bars: list[BaseBar],
        *,
        volume_poc: VolumePointOfControl | None = None,
    ) -> RangeBox | None:
        self._validate_bars(bars)
        candidate = self.base_detector.detect(bars)
        if candidate is None:
            return None
        window = self._window(bars, candidate)
        tolerance = self.config.contact_tolerance_adr * window[-1].adr20
        episodes = self._episodes(window, candidate, tolerance)
        if episodes is None:
            return None
        lower_count = sum(item.boundary is RangeBoundary.LOWER for item in episodes)
        upper_count = sum(item.boundary is RangeBoundary.UPPER for item in episodes)
        if lower_count < self.config.minimum_lower_episodes:
            return None
        if upper_count < self.config.minimum_upper_episodes:
            return None
        first, last = window[0].candle, window[-1].candle
        known_at = last.close_time
        if volume_poc is not None and volume_poc.known_at > known_at:
            raise ValueError("volume POC is future information")
        identity = {
            "base_instance_id": candidate.instance_id,
            "episodes": episodes,
            "volume_poc": volume_poc,
            "config_hash": self.config.config_hash,
            "pattern_version": "7A.1.0",
        }
        return RangeBox(
            box_id=deterministic_id("range_box", identity),
            base_instance_id=candidate.instance_id,
            symbol=first.symbol,
            timeframe=first.timeframe,
            start_candle_id=first.candle_id,
            end_candle_id=last.candle_id,
            start_time=first.open_time,
            end_time=last.close_time,
            known_at=known_at,
            lower=candidate.lower,
            upper=candidate.upper,
            geometric_midpoint=(candidate.lower + candidate.upper) / Decimal(2),
            volume_poc=volume_poc,
            episodes=episodes,
            lower_episode_count=lower_count,
            upper_episode_count=upper_count,
            width_adr=candidate.width_adr,
            net_drift_adr=candidate.net_drift_adr,
            overlap_score=candidate.overlap_score,
            atr_compression=candidate.atr_compression,
            quality=candidate.quality,
            parent_box_id=None,
            config_hash=self.config.config_hash,
            code_version=self.code_version,
        )

    @staticmethod
    def _validate_bars(bars: list[BaseBar]) -> None:
        if not bars:
            raise ValueError("bars are required")
        first = bars[0].candle
        previous_close: datetime | None = None
        candle_ids: set[str] = set()
        for bar in bars:
            candle = bar.candle
            if candle.symbol != first.symbol or candle.timeframe is not first.timeframe:
                raise ValueError("bars must share symbol and timeframe")
            if not candle.is_complete:
                raise ValueError("range detection accepts completed candles only")
            if previous_close is not None and candle.open_time < previous_close:
                raise ValueError("bars must be strictly chronological and nonoverlapping")
            if candle.candle_id in candle_ids:
                raise ValueError("duplicate candle identity")
            if bar.adr20 <= 0 or bar.atr10 <= 0:
                raise ValueError("ADR and ATR inputs must be positive")
            previous_close = candle.close_time
            candle_ids.add(candle.candle_id)

    @staticmethod
    def _window(bars: list[BaseBar], candidate: BaseCandidate) -> list[BaseBar]:
        by_id = {item.candle.candle_id: index for index, item in enumerate(bars)}
        start = by_id[candidate.start_candle_id]
        end = by_id[candidate.end_candle_id]
        return bars[start : end + 1]

    @staticmethod
    def _episodes(
        window: list[BaseBar],
        candidate: BaseCandidate,
        tolerance: Decimal,
    ) -> tuple[BoundaryEpisode, ...] | None:
        evidence: list[BoundaryEpisode] = []
        active_side: RangeBoundary | None = None
        active_ids: list[str] = []
        active_known_at: datetime | None = None

        def finish() -> None:
            nonlocal active_ids, active_known_at
            if active_side is not None and active_known_at is not None:
                evidence.append(
                    BoundaryEpisode(active_side, tuple(active_ids), active_known_at)
                )
            active_ids = []
            active_known_at = None

        for bar in window:
            lower_contact = bar.candle.low <= candidate.lower + tolerance
            upper_contact = bar.candle.high >= candidate.upper - tolerance
            if lower_contact and upper_contact:
                return None
            side = (
                RangeBoundary.LOWER
                if lower_contact
                else RangeBoundary.UPPER if upper_contact else None
            )
            if side is None:
                continue
            if active_side is side:
                active_ids.append(bar.candle.candle_id)
                active_known_at = bar.candle.close_time
                continue
            finish()
            active_side = side
            active_ids = [bar.candle.candle_id]
            active_known_at = bar.candle.close_time
        finish()
        return tuple(evidence)


_TIMEFRAME_RANK = {
    Timeframe.HOUR_1: 0,
    Timeframe.HOUR_4: 1,
    Timeframe.DAY_1: 2,
    Timeframe.WEEK_1: 3,
}


def assign_parent_box(child: RangeBox, candidates: list[RangeBox]) -> RangeBox:
    """Attach the narrowest causal containing box without changing box identity."""

    eligible = [
        item
        for item in candidates
        if item.box_id != child.box_id
        and item.symbol == child.symbol
        and item.known_at < child.known_at
        and _TIMEFRAME_RANK[item.timeframe] >= _TIMEFRAME_RANK[child.timeframe]
        and item.lower <= child.lower
        and item.upper >= child.upper
        and item.upper - item.lower > child.upper - child.lower
    ]
    if not eligible:
        return child
    parent = min(eligible, key=lambda item: (item.upper - item.lower, item.box_id))
    return replace(child, parent_box_id=parent.box_id)
