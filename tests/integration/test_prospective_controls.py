from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from tests.unit.test_prospective_controls import CONTROLS, PORTFOLIO, inputs
from tests.unit.test_prospective_entry import CAL, bar

from trading_system.execution_sim.prospective_control_registry import ProspectiveControlRegistry
from trading_system.execution_sim.prospective_controls import (
    assess_prospective_controls,
    load_prospective_controls_config,
)
from trading_system.execution_sim.prospective_positions import OfflineShadowPositions
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import load_portfolio_config


def test_control_receipt_is_immutable_restart_safe_and_opens_controlled(
    tmp_path: Path,
) -> None:
    path = tmp_path / "controls.sqlite"
    request, assessment, state, candidate = inputs()
    assert assessment.fill_price is not None
    with SQLiteRepository(path) as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        registry = ProspectiveControlRegistry(repo)
        controls = registry.assess(
            entry=request, entry_assessment=assessment, portfolio_state=state,
            candidate=candidate, portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=assessment.known_at,
        )
        assert registry.assess(
            entry=request, entry_assessment=assessment, portfolio_state=state,
            candidate=candidate, portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=assessment.known_at,
        ) == controls
        trade_id = OfflineShadowPositions(repo).open_controlled(
            request, assessment, controls,
        )
        assert trade_id
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_control_assessments")
    with SQLiteRepository(path) as repo:
        repo.migrate()
        assert OfflineShadowPositions(repo).open_controlled(
            request, assessment, controls,
        ) == trade_id


def test_rejected_or_unstored_control_cannot_open_position(tmp_path: Path) -> None:
    request, assessment, state, candidate = inputs()
    with SQLiteRepository(tmp_path / "rejected.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        rejected = ProspectiveControlRegistry(repo).assess(
            entry=request, entry_assessment=assessment,
            portfolio_state=replace(state, equity=state.equity / 200),
            candidate=candidate, portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=assessment.known_at,
        )
        with pytest.raises(ValueError, match="approved offline"):
            OfflineShadowPositions(repo).open_controlled(request, assessment, rejected)

    with SQLiteRepository(tmp_path / "unstored.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        controls = assess_prospective_controls(
            entry=request, entry_assessment=assessment, portfolio_state=state,
            candidate=candidate, portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
        )
        with pytest.raises(ValueError, match="unavailable or does not match"):
            OfflineShadowPositions(repo).open_controlled(request, assessment, controls)
