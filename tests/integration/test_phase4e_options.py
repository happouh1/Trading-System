from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from tests.integration.test_phase4c_options import _screen
from tests.unit.test_phase4c import CONFIG as PHASE4C_CONFIG
from tests.unit.test_phase4c import validation_case

from trading_system.options import (
    OptionsCapitalEngine,
    OptionsRegistry,
    OptionsValidationEngine,
    load_options_capital_config,
    load_options_validation_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "options.phase4e.v1.yaml"


def test_phase4e_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "phase4e.sqlite"
    snapshot, screen_result = _screen()
    case = validation_case(screen_result_id=screen_result.result_id)
    validation = OptionsValidationEngine(load_options_validation_config(PHASE4C_CONFIG))
    result = validation.evaluate(case)
    report, events = OptionsCapitalEngine(load_options_capital_config(CONFIG)).evaluate(
        (case,),
        (result,),
        starting_cash=Decimal("1000"),
        source_revision="sha256:phase4e-integration",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        registry.insert_snapshot(snapshot)
        registry.insert_result(screen_result)
        registry.insert_validation_case(case)
        registry.insert_validation_result(result)
        assert registry.insert_capital_run(report)
        assert not registry.insert_capital_run(report)
        for event in events:
            assert registry.insert_capital_event(event)
            assert not registry.insert_capital_event(event)
        assert registry.insert_capital_report(report)
        assert not registry.insert_capital_report(report)
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        assert len(registry.capital_event_payloads(report.run_id)) == 2
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_capital_run(
                replace(report, source_revision="sha256:conflicting")
            )


def test_phase4e_migration_copies_are_identical() -> None:
    root_copy = ROOT / "migrations" / "021_phase_4e_option_capital.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "021_phase_4e_option_capital.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()
