from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_phase7a_range_reclaim import fixture_bars
from tests.unit.test_phase7b_range_research import replay
from trading_system.domain import Direction, PatternEvent, PatternState
from trading_system.patterns import (
    RangeBoundary,
    RangeBox,
    RangeTriggerConfig,
    RangeTriggerConfigError,
    compose_range_reclaim_evidence,
    load_range_trigger_config,
)

ROOT = Path(__file__).parents[2]


def range_box() -> RangeBox:
    box = replay().detector.detect(fixture_bars())
    assert box is not None
    return box


def accepted_event(
    *,
    direction: Direction = Direction.LONG,
    reference: Decimal | None = None,
    hours_after: int = 24,
) -> PatternEvent:
    box = range_box()
    level = box.lower if reference is None else reference
    return PatternEvent(
        event_id=f"event-{direction.value}-{level}-{hours_after}",
        run_id="run-7d",
        observation_id="observation-7d",
        symbol=box.symbol,
        timeframe=box.timeframe,
        known_at=box.known_at + timedelta(hours=hours_after),
        pattern_family="RECLAIM",
        pattern_name=(
            "BULLISH_RECLAIM" if direction is Direction.LONG else "BEARISH_RECLAIM"
        ),
        pattern_version="1.0.0",
        instance_id="reclaim-instance-7d",
        prior_state=PatternState.PENDING,
        new_state=PatternState.ACCEPTED,
        direction=direction,
        reference_level=level,
        features={},
        evidence_candle_ids=("evidence-candle-7d",),
        reason_codes=("RECLAIM_ACCEPTED",),
        config_hash="sha256:event",
        code_version="test",
    )


def config() -> RangeTriggerConfig:
    return load_range_trigger_config(ROOT / "config/range_reclaim.phase7d.v1.yaml")


def test_exact_accepted_reclaims_map_to_directional_boundaries() -> None:
    box = range_box()
    long_event = accepted_event()
    short_event = accepted_event(direction=Direction.SHORT, reference=box.upper)
    evidence = compose_range_reclaim_evidence(
        config(), boxes=(box,), events=(long_event, short_event)
    )
    assert {item.boundary for item in evidence} == {
        RangeBoundary.LOWER,
        RangeBoundary.UPPER,
    }
    assert {item.direction for item in evidence} == {Direction.LONG, Direction.SHORT}
    assert all(item.known_at > item.box_known_at for item in evidence)


def test_nonexact_wrong_state_and_noncausal_events_do_not_match() -> None:
    box = range_box()
    wrong_price = accepted_event(reference=box.lower + 1)
    pending = replace(accepted_event(), event_id="pending", new_state=PatternState.PENDING)
    same_time = replace(accepted_event(), event_id="same-time", known_at=box.known_at)
    assert compose_range_reclaim_evidence(
        config(), boxes=(box,), events=(wrong_price, pending, same_time)
    ) == ()


def test_input_permutations_normalize_and_overlapping_matches_are_retained() -> None:
    box = range_box()
    second = replace(box, box_id="overlapping-box")
    events = (accepted_event(direction=Direction.SHORT, reference=box.upper), accepted_event())
    first = compose_range_reclaim_evidence(config(), boxes=(box, second), events=events)
    reordered = compose_range_reclaim_evidence(
        config(), boxes=(second, box), events=tuple(reversed(events))
    )
    assert first == reordered
    assert len(first) == 4
    with pytest.raises(ValueError, match="identities must be unique"):
        compose_range_reclaim_evidence(config(), boxes=(box, box), events=events)


def test_phase7d_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7d.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["entry_rule_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeTriggerConfigError, match="evidence-only"):
        load_range_trigger_config(unsafe)
