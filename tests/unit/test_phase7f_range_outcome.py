from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_features import daily_candle
from tests.unit.test_phase7d_range_trigger import accepted_event, range_box
from tests.unit.test_phase7d_range_trigger import config as trigger_config
from tests.unit.test_phase7e_range_entry import config as entry_config
from trading_system.domain import Candle
from trading_system.patterns import (
    RangeEntryContext,
    RangeEntryStatus,
    RangeOutcomeConfig,
    RangeOutcomeConfigError,
    RangeResearchEntry,
    compose_range_reclaim_evidence,
    label_range_entries,
    load_range_outcome_config,
    materialize_range_entries,
)

ROOT = Path(__file__).parents[2]
D = Decimal


def config() -> RangeOutcomeConfig:
    return load_range_outcome_config(ROOT / "config/range_reclaim.phase7f.v1.yaml")


def filled_entry() -> RangeResearchEntry:
    box = range_box()
    evidence = compose_range_reclaim_evidence(
        trigger_config(), boxes=(box,), events=(accepted_event(),)
    )[0]
    context = RangeEntryContext(evidence.evidence_id, evidence.known_at, D("2"), D("2"))
    candle = replace(daily_candle(49), open=D("99"), raw_open=D("99"))
    return materialize_range_entries(
        entry_config(), evidence=(evidence,), contexts=(context,), candles=(candle,)
    )[0]


def outcome_candles() -> tuple[Candle, ...]:
    return tuple(
        replace(daily_candle(index), open=D("99"), raw_open=D("99"))
        if index == 49
        else daily_candle(index)
        for index in range(49, 55)
    )


def test_every_mature_horizon_is_labeled_with_two_sided_slippage() -> None:
    entry = filled_entry()
    outcomes = label_range_entries(
        config(), entries=(entry,), boxes=(range_box(),), candles=outcome_candles()
    )
    assert [item.horizon_bars for item in outcomes] == [1, 3, 5]
    first = outcomes[0]
    assert first.exit_close == D("100")
    assert first.simulated_exit_price == D("99.96")
    assert first.gross_directional_return == D("1") / D("99")
    assert first.net_directional_return == D("0.92") / D("99.04")
    assert first.maximum_favorable_box_units == D("0.98")
    assert first.maximum_adverse_box_units == D("0.02")


def test_cancelled_entries_have_no_outcomes_and_immature_horizons_are_omitted() -> None:
    entry = filled_entry()
    cancelled = replace(
        entry,
        entry_id="cancelled-entry",
        status=RangeEntryStatus.CANCELLED_ADVERSE_GAP,
        simulated_fill_price=None,
    )
    assert label_range_entries(
        config(), entries=(cancelled,), boxes=(range_box(),), candles=outcome_candles()
    ) == ()
    outcomes = label_range_entries(
        config(), entries=(entry,), boxes=(range_box(),), candles=outcome_candles()[:2]
    )
    assert [item.horizon_bars for item in outcomes] == [1]


def test_input_permutations_normalize_and_source_mismatch_fails_closed() -> None:
    entry = filled_entry()
    candles = outcome_candles()
    assert label_range_entries(
        config(), entries=(entry,), boxes=(range_box(),), candles=candles
    ) == label_range_entries(
        config(), entries=(entry,), boxes=(range_box(),), candles=tuple(reversed(candles))
    )
    bad = replace(entry, opening_price=D("98"))
    with pytest.raises(ValueError, match="disagrees"):
        label_range_entries(config(), entries=(bad,), boxes=(range_box(),), candles=candles)


def test_phase7f_config_cannot_expand_authority(tmp_path: Path) -> None:
    path = ROOT / "config/range_reclaim.phase7f.v1.yaml"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority"]["scoring_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeOutcomeConfigError, match="research-only"):
        load_range_outcome_config(unsafe)
