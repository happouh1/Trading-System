from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.integration.test_phase4c_options import _screen
from tests.unit.test_phase4c import CONFIG as PHASE4C_CONFIG
from tests.unit.test_phase4c import validation_case
from tests.unit.test_phase4d import small_config

from trading_system.cli.main import main
from trading_system.options import (
    OptionExperimentPartition,
    OptionExperimentStage,
    OptionExperimentTransition,
    OptionsExperimentEngine,
    OptionsRegistry,
    OptionsValidationEngine,
    load_options_experiment_config,
    load_options_validation_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]


def test_phase4d_registry_is_append_only_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "phase4d.sqlite"
    config = small_config(tmp_path)
    raw = load_options_experiment_config(config)
    active = OptionsExperimentEngine(
        raw,
        OptionsValidationEngine(load_options_validation_config(PHASE4C_CONFIG)),
    )
    snapshot, screen_result = _screen()
    case = validation_case(screen_result_id=screen_result.result_id)
    sessions = tuple(date(2026, 8, 28) + timedelta(days=index) for index in range(10))
    definition = active.define(
        source_revision="sha256:phase4d-integration",
        sessions=sessions,
        cases=(case,),
    )
    folds = active.folds(definition)
    fold = folds[0]
    result = active.validation_engine.evaluate(case)
    assignments = active.assignments(definition, fold, (case,))
    development = tuple(
        active.evaluate_partition(definition, fold, partition, (case,))
        for partition in (
            OptionExperimentPartition.TRAIN,
            OptionExperimentPartition.VALIDATION,
        )
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        registry.insert_snapshot(snapshot)
        registry.insert_result(screen_result)
        registry.insert_validation_case(case)
        registry.insert_validation_result(result)
        assert registry.insert_experiment(definition)
        assert not registry.insert_experiment(definition)
        for fold_item in folds:
            registry.insert_experiment_fold(fold_item)
        for assignment_item in assignments:
            registry.insert_experiment_assignment(assignment_item)
        for evaluation_item in development:
            registry.insert_fold_evaluation(evaluation_item)
        registry.insert_experiment_transition(
            OptionExperimentTransition.create(
                definition.experiment_id,
                OptionExperimentStage.DEFINED,
                OptionExperimentStage.DEVELOPMENT_EVALUATED,
            )
        )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        assert registry.experiment_stage(definition.experiment_id) is (
            OptionExperimentStage.DEVELOPMENT_EVALUATED
        )
        assert len(registry.experiment_evaluation_payloads(definition.experiment_id)) == 2
        with pytest.raises(ValueError, match="conflicting"):
            registry.insert_experiment(replace(definition, source_revision="sha256:changed"))


def test_phase4d_migration_copies_are_identical() -> None:
    root_copy = ROOT / "migrations" / "020_phase_4d_option_experiments.sql"
    package_copy = (
        ROOT
        / "src"
        / "trading_system"
        / "persistence"
        / "migrations"
        / "020_phase_4d_option_experiments.sql"
    )
    assert root_copy.read_bytes() == package_copy.read_bytes()


def _number(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _case_payload(case: object) -> dict[str, object]:
    from trading_system.options import OptionValidationCase

    if not isinstance(case, OptionValidationCase):
        raise TypeError("expected option validation case")

    def mark_payload(mark: object) -> dict[str, object]:
        from trading_system.options import OptionMark

        if not isinstance(mark, OptionMark):
            raise TypeError("expected option mark")
        contract = mark.contract
        quote = contract.quote
        return {
            "snapshot_id": mark.snapshot_id,
            "as_of": mark.as_of.isoformat(),
            "source": mark.source,
            "source_revision": mark.source_revision,
            "contract": {
                "contract_id": contract.contract_id,
                "occ_symbol": contract.occ_symbol,
                "underlying": contract.underlying,
                "expiration": contract.expiration.isoformat(),
                "strike": _number(contract.strike),
                "right": contract.right.value,
                "multiplier": _number(contract.multiplier),
                "exercise_style": contract.exercise_style.value,
                "settlement_type": contract.settlement_type.value,
                "standard_contract": contract.standard_contract,
                "quote": {
                    "observed_at": quote.observed_at.isoformat(),
                    "bid": _number(quote.bid),
                    "ask": _number(quote.ask),
                    "last": _number(quote.last),
                    "volume": quote.volume,
                    "open_interest": quote.open_interest,
                    "implied_volatility": _number(quote.implied_volatility),
                    "delta": _number(quote.delta),
                    "gamma": _number(quote.gamma),
                    "theta": _number(quote.theta),
                    "vega": _number(quote.vega),
                },
            },
        }

    return {
        "screen_result_id": case.screen_result_id,
        "screen_known_at": case.screen_known_at.isoformat(),
        "selected_contract_id": case.selected_contract_id,
        "horizon": case.horizon.value,
        "direction": case.direction.value,
        "quantity": case.quantity,
        "entry": mark_payload(case.entry),
        "exit": mark_payload(case.exit),
        "exit_reason": case.exit_reason,
        "source_revision": case.source_revision,
    }


def test_phase4d_cli_enforces_freeze_before_test_and_completes(tmp_path: Path) -> None:
    database = tmp_path / "phase4d-cli.sqlite"
    config = small_config(tmp_path)
    snapshot, screen_result = _screen()
    case = validation_case(screen_result_id=screen_result.result_id)
    session_dates = tuple(date(2026, 8, 28) + timedelta(days=index) for index in range(10))
    source = tmp_path / "experiment.json"
    source.write_text(
        json.dumps(
            {
                "source_revision": "sha256:phase4d-cli",
                "sessions": [item.isoformat() for item in session_dates],
                "cases": [_case_payload(case)],
            }
        ),
        encoding="utf-8",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = OptionsRegistry(repository)
        registry.insert_snapshot(snapshot)
        registry.insert_result(screen_result)
    common = [
        "--config",
        str(config),
        "--backtest-config",
        str(PHASE4C_CONFIG),
        "--input",
        str(source),
        "--database",
        str(database),
    ]
    assert main(["options", "experiment-define", *common]) == 0
    with pytest.raises(ValueError, match="FROZEN"):
        main(["options", "experiment-test", *common])
    assert main(["options", "experiment-development", *common]) == 0
    assert main(["options", "experiment-freeze", *common]) == 0
    assert main(["options", "experiment-test", *common]) == 0
    assert main(["options", "experiment-complete", *common]) == 0

    active = OptionsExperimentEngine(
        load_options_experiment_config(config),
        OptionsValidationEngine(load_options_validation_config(PHASE4C_CONFIG)),
    )
    definition = active.define(
        source_revision="sha256:phase4d-cli",
        sessions=session_dates,
        cases=(case,),
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert OptionsRegistry(repository).experiment_stage(definition.experiment_id) is (
            OptionExperimentStage.COMPLETE
        )
