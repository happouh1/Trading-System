from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from tests.unit.test_prospective_entry import CAL, D, bar, entry
from trading_system.execution_sim.prospective import (
    EntryAssessment,
    ProspectiveEntry,
    assess_entry,
)
from trading_system.execution_sim.prospective_controls import (
    ProspectiveControlsConfigError,
    assess_prospective_controls,
    load_prospective_controls_config,
)
from trading_system.portfolio import (
    PortfolioAction,
    PortfolioCandidate,
    PortfolioState,
    load_portfolio_config,
)

ROOT = Path(__file__).parents[2]
CONTROLS = ROOT / "config" / "prospective_controls.v1.yaml"
PORTFOLIO = ROOT / "config" / "portfolio.phase4a.v1.yaml"
DEFAULT_EQUITY = Decimal("100000")


def inputs(
    *, equity: Decimal = DEFAULT_EQUITY,
) -> tuple[ProspectiveEntry, EntryAssessment, PortfolioState, PortfolioCandidate]:
    request = entry()
    candle = bar()
    assessment = assess_entry(
        request, calendar=CAL, candle=candle,
        received_at=candle.close_time, as_of=candle.close_time,
    )
    assert assessment.fill_price is not None
    state = PortfolioState("prospective-portfolio", assessment.known_at, equity)
    candidate = PortfolioCandidate(
        request.decision_id, request.plan.plan_id, request.plan.symbol,
        request.plan.direction, assessment.known_at, 10, assessment.fill_price,
        request.plan.initial_stop, D(1), D("10000000"), "TECHNOLOGY",
        "sha256:point-in-time-portfolio",
    )
    return request, assessment, state, candidate


def test_config_is_strict_offline_spec_default(tmp_path: Path) -> None:
    config = load_prospective_controls_config(CONTROLS)
    assert config.config_hash.startswith("sha256:")
    raw = json.loads(CONTROLS.read_text(encoding="utf-8"))
    raw["costs"]["fee_per_share_per_side"] = "0.01"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveControlsConfigError, match="specification default"):
        load_prospective_controls_config(path)
    raw["costs"]["fee_per_share_per_side"] = 0
    raw["authority"]["broker_writes_enabled"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveControlsConfigError, match="offline-only"):
        load_prospective_controls_config(path)


def test_actual_fill_is_accepted_with_declared_zero_fee_policy() -> None:
    request, assessment, state, candidate = inputs()
    result = assess_prospective_controls(
        entry=request, entry_assessment=assessment, portfolio_state=state,
        candidate=candidate, portfolio_config=load_portfolio_config(PORTFOLIO),
        controls_config=load_prospective_controls_config(CONTROLS),
    )
    assert result.status == "CONTROL_APPROVED"
    assert result.reason_codes == ()
    assert result.portfolio_assessment.action is PortfolioAction.ACCEPT
    assert result.fee_per_share_per_side == 0
    assert result.estimated_round_trip_fees == 0
    assert result.fees_status == "SPEC_DEFAULT_ZERO_DECLARED"
    assert result.spread_status == "COMBINED_IN_DECLARED_SLIPPAGE"
    assert not result.qualifying_completed_trade
    assert not result.broker_write_performed and not result.cohort_activated


def test_portfolio_rejection_is_preserved_and_inputs_must_bind_fill() -> None:
    request, assessment, _, candidate = inputs()
    state = PortfolioState("prospective-portfolio", assessment.known_at, D(500))
    result = assess_prospective_controls(
        entry=request, entry_assessment=assessment, portfolio_state=state,
        candidate=candidate, portfolio_config=load_portfolio_config(PORTFOLIO),
        controls_config=load_prospective_controls_config(CONTROLS),
    )
    assert result.status == "CONTROL_REJECTED_PORTFOLIO"
    assert "PORTFOLIO_POSITION_EXPOSURE" in result.reason_codes
    with pytest.raises(ValueError, match="bind the modelled entry"):
        assess_prospective_controls(
            entry=request, entry_assessment=assessment, portfolio_state=state,
            candidate=replace(candidate, entry_price=D(100)),
            portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
        )
