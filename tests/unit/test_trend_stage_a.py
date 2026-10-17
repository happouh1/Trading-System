from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.research import (
    StageAConfigError,
    StageAObservation,
    StageAState,
    StageATimeBucket,
    StageAVolumeBand,
    assess_stage_a,
    load_stage_a_config,
)

D = Decimal
ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "trend_stage_a.v1.yaml"


def observation(**changes: object) -> StageAObservation:
    values: dict[str, object] = {
        "symbol": "SWKS",
        "session_date": date(2026, 9, 4),
        "known_at": datetime(2026, 9, 4, 13, 45, tzinfo=UTC),
        "close": D("74.11"),
        "ema8": D("69.96"),
        "ema21": D("68"),
        "ema50": D("64"),
        "recent_volume_surge": D("3.7"),
        "off_20d_high_pct": D("-0.9"),
        "adr20_pct": D("4.3"),
        "gap_pct": D("1.0"),
    }
    values.update(changes)
    return StageAObservation(**values)  # type: ignore[arg-type]


def test_config_is_research_only_and_versioned() -> None:
    config = load_stage_a_config(CONFIG)
    assert config.config_hash.startswith("sha256:")
    assert config.values["stage_a_version"] == "1.0.0"


def test_config_rejects_authority_expansion(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["broker_writes_enabled"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(StageAConfigError, match="research-only"):
        load_stage_a_config(path)


def test_clean_stage_a_is_qualified_with_stable_symbol_session_identity() -> None:
    config = load_stage_a_config(CONFIG)
    first = assess_stage_a(observation(), config)
    later = assess_stage_a(
        observation(known_at=datetime(2026, 9, 4, 18, 30, tzinfo=UTC)), config
    )
    assert first.state is StageAState.QUALIFIED
    assert first.entry_eligible is True
    assert first.volume_band is StageAVolumeBand.SUPPORTING
    assert first.time_bucket is StageATimeBucket.BEFORE_1000_ET
    assert first.observation_id == later.observation_id
    assert first.broker_write_performed is False


def test_extension_is_watch_not_entry_and_over_eight_is_overextended() -> None:
    config = load_stage_a_config(CONFIG)
    extended = assess_stage_a(observation(close=D("107"), ema8=D("100")), config)
    overextended = assess_stage_a(observation(close=D("109"), ema8=D("100")), config)
    assert extended.state is StageAState.EXTENDED_WATCH
    assert extended.setup_qualified is True
    assert extended.entry_eligible is False
    assert overextended.state is StageAState.OVEREXTENDED
    assert overextended.entry_eligible is False


def test_gap_warning_blocks_entry_but_does_not_erase_setup_quality() -> None:
    result = assess_stage_a(observation(gap_pct=D("3")), load_stage_a_config(CONFIG))
    assert result.state is StageAState.QUALIFIED
    assert result.setup_qualified is True
    assert result.entry_eligible is False
    assert "STAGE_A_GAP_CHASE_WARNING" in result.reason_codes


@pytest.mark.parametrize(
    ("item", "reason"),
    (
        (observation(close=D("4.99")), "STAGE_A_PRICE_BELOW_MINIMUM"),
        (observation(adr20_pct=D("3.49")), "STAGE_A_ADR_BELOW_MINIMUM"),
        (observation(recent_volume_surge=D("1.99")), "STAGE_A_VOLUME_SURGE_MISSING"),
        (observation(off_20d_high_pct=D("-3")), "STAGE_A_TOO_FAR_FROM_20D_HIGH"),
        (observation(ema21=D("63"), ema50=D("64")), "STAGE_A_FULL_BULL_STACK_MISSING"),
    ),
)
def test_base_setup_failures_are_explicit(item: StageAObservation, reason: str) -> None:
    result = assess_stage_a(item, load_stage_a_config(CONFIG))
    assert result.state is StageAState.NOT_QUALIFIED
    assert result.entry_eligible is False
    assert reason in result.reason_codes


def test_observation_rejects_noncausal_or_invalid_identity() -> None:
    with pytest.raises(ValueError, match="same ET day"):
        replace(observation(), session_date=date(2026, 9, 3))


def test_cli_assessment_is_offline_and_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "stage-a-input.json"
    path.write_text(
        json.dumps(
            {
                "symbol": "SWKS",
                "session_date": "2026-09-04",
                "known_at": "2026-09-04T13:45:00Z",
                "close": "74.11",
                "ema8": "69.96",
                "ema21": "68",
                "ema50": "64",
                "recent_volume_surge": "3.7",
                "off_20d_high_pct": "-0.9",
                "adr20_pct": "4.3",
                "gap_pct": "1.0",
            }
        ),
        encoding="utf-8",
    )
    assert main(["stage-a", "assess", "--config", str(CONFIG), "--input", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["state"] == "QUALIFIED"
    assert output["research_only"] is True
    assert output["broker_write_performed"] is False
