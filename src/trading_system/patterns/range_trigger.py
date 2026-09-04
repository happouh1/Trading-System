"""Compose accepted reclaim events with previously known range boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from trading_system.domain import Direction, PatternEvent, PatternState, Timeframe
from trading_system.patterns.range_reclaim import RangeBoundary, RangeBox
from trading_system.patterns.range_trigger_config import RangeTriggerConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RangeReclaimEvidence:
    evidence_id: str
    run_id: str
    box_id: str
    event_id: str
    observation_id: str
    symbol: str
    timeframe: Timeframe
    direction: Direction
    boundary: RangeBoundary
    reference_level: Decimal
    box_known_at: datetime
    known_at: datetime
    event_pattern_version: str
    box_config_hash: str
    event_config_hash: str
    evidence_config_hash: str
    code_version: str
    evidence_candle_ids: tuple[str, ...]
    evidence_version: str = "7D.1.0"

    def __post_init__(self) -> None:
        required = (
            self.evidence_id,
            self.run_id,
            self.box_id,
            self.event_id,
            self.observation_id,
            self.symbol,
            self.event_pattern_version,
            self.box_config_hash,
            self.event_config_hash,
            self.evidence_config_hash,
            self.code_version,
        )
        if not all(required):
            raise ValueError("complete range-reclaim evidence identity is required")
        _aware(self.box_known_at, "box_known_at")
        _aware(self.known_at, "known_at")
        if self.known_at <= self.box_known_at:
            raise ValueError("reclaim evidence must be known strictly after its box")
        if self.reference_level <= 0 or not self.reference_level.is_finite():
            raise ValueError("reference level must be finite and positive")
        expected_boundary = (
            RangeBoundary.LOWER if self.direction is Direction.LONG else RangeBoundary.UPPER
        )
        if self.direction is Direction.NONE or self.boundary is not expected_boundary:
            raise ValueError("direction and range boundary are inconsistent")
        if not self.evidence_candle_ids or len(set(self.evidence_candle_ids)) != len(
            self.evidence_candle_ids
        ):
            raise ValueError("unique candle evidence is required")
        if self.evidence_version != "7D.1.0":
            raise ValueError("evidence_version is fixed for Phase 7D")


def compose_range_reclaim_evidence(
    config: RangeTriggerConfig,
    *,
    boxes: tuple[RangeBox, ...],
    events: tuple[PatternEvent, ...],
) -> tuple[RangeReclaimEvidence, ...]:
    if len({box.box_id for box in boxes}) != len(boxes):
        raise ValueError("range box identities must be unique")
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("pattern event identities must be unique")
    ordered_boxes = tuple(sorted(boxes, key=lambda item: (item.known_at, item.box_id)))
    ordered_events = tuple(sorted(events, key=lambda item: (item.known_at, item.event_id)))
    result: list[RangeReclaimEvidence] = []
    for event in ordered_events:
        boundary = _eligible_boundary(event)
        if boundary is None or event.reference_level is None:
            continue
        for box in ordered_boxes:
            reference = box.lower if boundary is RangeBoundary.LOWER else box.upper
            if (
                box.symbol != event.symbol
                or box.timeframe is not event.timeframe
                or event.known_at <= box.known_at
                or event.reference_level != reference
            ):
                continue
            identity = (
                event.run_id,
                box.box_id,
                event.event_id,
                boundary,
                config.config_hash,
                "7D.1.0",
            )
            result.append(
                RangeReclaimEvidence(
                    deterministic_id("range_reclaim_evidence", identity),
                    event.run_id,
                    box.box_id,
                    event.event_id,
                    event.observation_id,
                    event.symbol,
                    event.timeframe,
                    event.direction,
                    boundary,
                    event.reference_level,
                    box.known_at,
                    event.known_at,
                    event.pattern_version,
                    box.config_hash,
                    event.config_hash,
                    config.config_hash,
                    event.code_version,
                    event.evidence_candle_ids,
                )
            )
    return tuple(sorted(result, key=lambda item: (item.known_at, item.evidence_id)))


def _eligible_boundary(event: PatternEvent) -> RangeBoundary | None:
    if (
        event.pattern_family != "RECLAIM"
        or event.new_state is not PatternState.ACCEPTED
        or event.reason_codes != ("RECLAIM_ACCEPTED",)
    ):
        return None
    if event.pattern_name == "BULLISH_RECLAIM" and event.direction is Direction.LONG:
        return RangeBoundary.LOWER
    if event.pattern_name == "BEARISH_RECLAIM" and event.direction is Direction.SHORT:
        return RangeBoundary.UPPER
    return None
