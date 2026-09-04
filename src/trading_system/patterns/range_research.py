"""Offline causal materialization and neutral outcomes for Phase 7B."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from trading_system.domain import Candle, Timeframe
from trading_system.patterns.bases import BaseBar
from trading_system.patterns.range_reclaim import (
    RangeBox,
    RangeBoxDetector,
    VolumePointOfControl,
)
from trading_system.patterns.range_research_config import RangeResearchConfig
from trading_system.serialization import deterministic_id


class RangeTerminalLocation(StrEnum):
    ABOVE = "ABOVE"
    INSIDE = "INSIDE"
    BELOW = "BELOW"


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RangeBoxOutcome:
    outcome_id: str
    box_id: str
    symbol: str
    timeframe: Timeframe
    horizon_bars: int
    label_available_at: datetime
    anchor_close: Decimal
    forward_return: Decimal
    maximum_upside_box_units: Decimal
    maximum_downside_box_units: Decimal
    terminal_location: RangeTerminalLocation
    future_candle_ids: tuple[str, ...]
    config_hash: str
    code_version: str
    label_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.outcome_id or not self.box_id or not self.symbol or not self.timeframe:
            raise ValueError("outcome identity and series are required")
        if self.horizon_bars <= 0 or len(self.future_candle_ids) != self.horizon_bars:
            raise ValueError("horizon must match future candle evidence")
        if len(set(self.future_candle_ids)) != len(self.future_candle_ids):
            raise ValueError("future candle evidence must be unique")
        _aware(self.label_available_at, "label_available_at")
        if self.anchor_close <= 0 or not self.anchor_close.is_finite():
            raise ValueError("anchor_close must be finite and positive")
        for name in (
            "forward_return",
            "maximum_upside_box_units",
            "maximum_downside_box_units",
        ):
            value = getattr(self, name)
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
        if self.maximum_upside_box_units < 0 or self.maximum_downside_box_units < 0:
            raise ValueError("excursions must be nonnegative")
        if not self.config_hash or not self.code_version:
            raise ValueError("config_hash and code_version are required")
        if self.label_version != "1.0.0":
            raise ValueError("label_version is fixed for Phase 7B")


def label_range_box(
    box: RangeBox,
    *,
    anchor_close: Decimal,
    future_candles: tuple[Candle, ...],
    config_hash: str,
    code_version: str,
) -> RangeBoxOutcome:
    if not future_candles:
        raise ValueError("future candles are required")
    previous_close = box.known_at
    for candle in future_candles:
        if (
            not candle.is_complete
            or candle.symbol != box.symbol
            or candle.timeframe is not box.timeframe
        ):
            raise ValueError("future candles must be complete and match the box series")
        if candle.close_time <= previous_close:
            raise ValueError("future candles must be strictly chronological and post-box")
        previous_close = candle.close_time
    width = box.upper - box.lower
    last = future_candles[-1]
    terminal = (
        RangeTerminalLocation.ABOVE
        if last.close > box.upper
        else RangeTerminalLocation.BELOW
        if last.close < box.lower
        else RangeTerminalLocation.INSIDE
    )
    evidence = tuple(candle.candle_id for candle in future_candles)
    return RangeBoxOutcome(
        outcome_id=deterministic_id(
            "range_box_outcome",
            (box.box_id, len(future_candles), evidence, config_hash, "1.0.0"),
        ),
        box_id=box.box_id,
        symbol=box.symbol,
        timeframe=box.timeframe,
        horizon_bars=len(future_candles),
        label_available_at=last.close_time,
        anchor_close=anchor_close,
        forward_return=(last.close - anchor_close) / anchor_close,
        maximum_upside_box_units=max(
            Decimal(0),
            max(candle.high for candle in future_candles) - anchor_close,
        )
        / width,
        maximum_downside_box_units=max(
            Decimal(0),
            anchor_close - min(candle.low for candle in future_candles),
        )
        / width,
        terminal_location=terminal,
        future_candle_ids=evidence,
        config_hash=config_hash,
        code_version=code_version,
    )


@dataclass(frozen=True, slots=True)
class RangeResearchResult:
    boxes: tuple[RangeBox, ...]
    outcomes: tuple[RangeBoxOutcome, ...]


class RangeResearchReplay:
    """Detect each prefix, then disclose outcomes only at completed horizons."""

    def __init__(
        self,
        detector: RangeBoxDetector,
        config: RangeResearchConfig,
        *,
        code_version: str,
    ) -> None:
        if not code_version:
            raise ValueError("code_version is required")
        self.detector = detector
        self.config = config
        self.code_version = code_version

    def run(
        self,
        bars: list[BaseBar],
        *,
        volume_poc_by_end_candle_id: Mapping[str, VolumePointOfControl] | None = None,
    ) -> RangeResearchResult:
        if not bars:
            raise ValueError("bars are required")
        known_ids = {bar.candle.candle_id for bar in bars}
        poc_by_id = volume_poc_by_end_candle_id or {}
        if any(key not in known_ids for key in poc_by_id):
            raise ValueError("volume POC mapping contains unknown candle identity")
        boxes: dict[str, RangeBox] = {}
        for end in range(1, len(bars) + 1):
            prefix = bars[:end]
            final_id = prefix[-1].candle.candle_id
            box = self.detector.detect(prefix, volume_poc=poc_by_id.get(final_id))
            if box is not None:
                boxes.setdefault(box.box_id, box)
        index_by_id = {bar.candle.candle_id: index for index, bar in enumerate(bars)}
        outcomes: list[RangeBoxOutcome] = []
        for box in boxes.values():
            end_index = index_by_id[box.end_candle_id]
            anchor_close = bars[end_index].candle.close
            for horizon in self.config.horizons(box.timeframe):
                future = bars[end_index + 1 : end_index + 1 + horizon]
                if len(future) != horizon:
                    continue
                outcomes.append(
                    label_range_box(
                        box,
                        anchor_close=anchor_close,
                        future_candles=tuple(item.candle for item in future),
                        config_hash=self.config.config_hash,
                        code_version=self.code_version,
                    )
                )
        ordered_boxes = tuple(sorted(boxes.values(), key=lambda item: (item.known_at, item.box_id)))
        ordered_outcomes = tuple(
            sorted(outcomes, key=lambda item: (item.label_available_at, item.outcome_id))
        )
        return RangeResearchResult(ordered_boxes, ordered_outcomes)
