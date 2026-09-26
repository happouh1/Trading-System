from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from tests.unit.test_prospective_controls import CONTROLS, PORTFOLIO, inputs
from tests.unit.test_prospective_entry import CAL, bar
from tests.unit.test_prospective_evidence import records

from trading_system.execution_sim.prospective_control_registry import ProspectiveControlRegistry
from trading_system.execution_sim.prospective_controls import load_prospective_controls_config
from trading_system.execution_sim.prospective_evidence import corroborate_prospective_inputs
from trading_system.execution_sim.prospective_evidence_registry import ProspectiveEvidenceRegistry
from trading_system.execution_sim.prospective_registry import ProspectiveEntryRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.portfolio import load_portfolio_config


def test_corroborated_inputs_are_immutable_and_feed_control_receipt(tmp_path: Path) -> None:
    request, assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    with SQLiteRepository(tmp_path / "evidence.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        registry = ProspectiveEvidenceRegistry(repo)
        result = registry.corroborate(
            entry=request, entry_assessment=assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
            planned_hold_sessions=10, as_of=assessment.known_at,
        )
        assert registry.corroborate(
            entry=request, entry_assessment=assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
            planned_hold_sessions=10, as_of=assessment.known_at,
        ) == result
        control = ProspectiveControlRegistry(repo).assess_evidence_bound(
            entry=request, entry_assessment=assessment, evidence=result,
            portfolio_config=load_portfolio_config(PORTFOLIO),
            controls_config=load_prospective_controls_config(CONTROLS),
            as_of=assessment.known_at,
        )
        assert control.status == "CONTROL_APPROVED"
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            repo.connection.execute("DELETE FROM prospective_evidence_receipts")


def test_unstored_evidence_cannot_drive_controls(tmp_path: Path) -> None:
    request, assessment, _, _ = inputs()
    p1, p2, m1, m2 = records()
    with SQLiteRepository(tmp_path / "unstored.sqlite") as repo:
        repo.migrate()
        ProspectiveEntryRegistry(repo).assess(
            request, calendar=CAL, candle=bar(), received_at=bar().close_time,
            as_of=bar().close_time,
        )
        result = corroborate_prospective_inputs(
            entry=request, entry_assessment=assessment,
            portfolio_evidence=(p1, p2), market_evidence=(m1, m2),
            planned_hold_sessions=10,
        )
        with pytest.raises(ValueError, match="unavailable or changed"):
            ProspectiveControlRegistry(repo).assess_evidence_bound(
                entry=request, entry_assessment=assessment, evidence=result,
                portfolio_config=load_portfolio_config(PORTFOLIO),
                controls_config=load_prospective_controls_config(CONTROLS),
                as_of=assessment.known_at,
            )
