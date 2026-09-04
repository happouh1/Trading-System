from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_features import daily_candle
from tests.unit.test_phase7d_range_trigger import accepted_event, range_box
from tests.unit.test_phase7d_range_trigger import config as trigger_config
from trading_system.patterns import (
    RangeEntryConfig,
    RangeEntryConfigError,
    RangeEntryContext,
    RangeEntryStatus,
    RangeReclaimEvidence,
    compose_range_reclaim_evidence,
    load_range_entry_config,
    materialize_range_entries,
)

ROOT = Path(__file__).parents[2]
D = Decimal


def config() -> RangeEntryConfig:
    return load_range_entry_config(ROOT / "config/range_reclaim.phase7e.v1.yaml")


def evidence() -> RangeReclaimEvidence:
    box = range_box()
    return compose_range_reclaim_evidence(
        trigger_config(), boxes=(box,), events=(accepted_event(),)
    )[0]


def context() -> RangeEntryContext:
    item = evidence()
    return RangeEntryContext(item.evidence_id, item.known_at, D("2"), D("2"))


def test_next_open_fill_uses_existing_execution_slippage_proxy() -> None:
    item = evidence()
    candle = replace(
        daily_candle(49),
        open=D("99"),
        raw_open=D("99"),
    )
    result = materialize_range_entries(
        config(), evidence=(item,), contexts=(context(),), candles=(candle,)
    )[0]
    assert result.status is RangeEntryStatus.FILLED
    assert result.entry_time == candle.open_time
    assert result.slippage == D("0.04")
    assert result.simulated_fill_price == D("99.04")


def test_adverse_gap_cancels_without_a_fill() -> None:
    item = evidence()
    result = materialize_range_entries(
        config(), evidence=(item,), contexts=(context(),), candles=(daily_candle(49),)
    )[0]
    assert result.status is RangeEntryStatus.CANCELLED_ADVERSE_GAP
    assert result.adverse_gap_adr20 == D("0.5")
    assert result.simulated_fill_price is None


def test_future_context_is_rejected_and_immature_entry_is_omitted() -> None:
    item = evidence()
    future_context = replace(context(), known_at=item.known_at + timedelta(seconds=1))
    with pytest.raises(ValueError, match="future information"):
        materialize_range_entries(
            config(), evidence=(item,), contexts=(future_context,), candles=(daily_candle(49),)
        )
    assert materialize_range_entries(
        config(), evidence=(item,), contexts=(context(),), candles=(daily_candle(48),)
    ) == ()


def test_input_permutations_normalize_and_duplicates_fail_closed() -> None:
    item = evidence()
    second = replace(item, evidence_id="second-evidence")
    contexts = (context(), replace(context(), evidence_id="second-evidence"))
    candles = (daily_candle(50), daily_candle(49))
    first = materialize_range_entries(
        config(), evidence=(item, second), contexts=contexts, candles=candles
    )
    reordered = materialize_range_entries(
        config(), evidence=(second, item), contexts=tuple(reversed(contexts)),
        candles=tuple(reversed(candles)),
    )
    assert first == reordered
    with pytest.raises(ValueError, match="candle identities must be unique"):
        materialize_range_entries(
            config(), evidence=(item,), contexts=(context(),),
            candles=(daily_candle(49), daily_candle(49)),
        )


def test_phase7e_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7e.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeEntryConfigError, match="research-only"):
        load_range_entry_config(unsafe)
