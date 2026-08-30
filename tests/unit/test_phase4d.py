from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase4c import CONFIG as PHASE4C_CONFIG
from tests.unit.test_phase4c import series
from trading_system.cli.main import main
from trading_system.domain import Direction
from trading_system.options import (
    OptionExperimentPartition,
    OptionHorizon,
    OptionsExperimentConfigError,
    OptionsExperimentEngine,
    OptionsValidationEngine,
    OptionValidationCase,
    load_options_experiment_config,
    load_options_validation_config,
)
from trading_system.options.validation import OptionMark

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "options.phase4d.v1.yaml"


def small_config(tmp_path: Path, *, minimum_sample: int = 1) -> Path:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["folds"] = {
        "minimum_train_sessions": 3,
        "validation_sessions": 1,
        "test_sessions": 1,
        "step_sessions": 1,
        "embargo_sessions": 1,
    }
    raw["evaluation"]["minimum_partition_sample"] = minimum_sample
    path = tmp_path / "phase4d.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def sessions() -> tuple[date, ...]:
    return tuple(date(2026, 9, day) for day in range(1, 11))


def experiment_case(
    name: str,
    screen_day: int,
    *,
    exit_day: int | None = None,
) -> OptionValidationCase:
    screen_at = datetime(2026, 9, screen_day, 14, tzinfo=UTC)
    entry_at = screen_at + timedelta(hours=1)
    resolved_exit_day = screen_day if exit_day is None else exit_day
    exit_at = datetime(2026, 9, resolved_exit_day, 16, tzinfo=UTC)
    return OptionValidationCase.create(
        screen_result_id=f"screen-{name}",
        screen_known_at=screen_at,
        selected_contract_id="AAPL-20261016-100-C",
        horizon=OptionHorizon.FORTY_FIVE_DTE,
        direction=Direction.LONG,
        quantity=1,
        entry=OptionMark(f"entry-{name}", entry_at, "fixture", f"entry-{name}", series(entry_at)),
        exit=OptionMark(f"exit-{name}", exit_at, "fixture", f"exit-{name}", series(exit_at)),
        exit_reason="EXTERNAL_VALIDATION_HORIZON",
        source_revision=f"sha256:{name}",
    )


def engine(config: Path) -> OptionsExperimentEngine:
    return OptionsExperimentEngine(
        load_options_experiment_config(config),
        OptionsValidationEngine(load_options_validation_config(PHASE4C_CONFIG)),
    )


def test_phase4d_config_locks_research_only_authority(tmp_path: Path) -> None:
    assert load_options_experiment_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["options_execution_enabled"] = True
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(OptionsExperimentConfigError, match="research-only"):
        load_options_experiment_config(invalid)


def test_phase4d_config_cli_is_offline_and_deterministic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["options", "validate-experiment-config", "--config", str(CONFIG)]) == 0
    output = capsys.readouterr().out
    assert '"valid":true' in output
    assert '"config_hash":"sha256:' in output


def test_folds_are_expanding_deterministic_and_embargoed(tmp_path: Path) -> None:
    active = engine(small_config(tmp_path))
    cases = (experiment_case("train", 1), experiment_case("test", 7))
    definition = active.define(
        source_revision="sha256:dataset",
        sessions=sessions(),
        cases=cases,
    )
    folds = active.folds(definition)
    assert len(folds) == 4
    assert folds[0].train_start == date(2026, 9, 1)
    assert folds[0].train_end == date(2026, 9, 3)
    assert folds[0].validation_start == date(2026, 9, 5)
    assert folds[0].test_start == date(2026, 9, 7)
    reversed_definition = active.define(
        source_revision="sha256:dataset",
        sessions=sessions(),
        cases=tuple(reversed(cases)),
    )
    assert reversed_definition == definition
    assert active.folds(reversed_definition) == folds


def test_label_must_be_available_by_partition_cutoff(tmp_path: Path) -> None:
    active = engine(small_config(tmp_path))
    cases = (
        experiment_case("train", 1, exit_day=2),
        experiment_case("validation-late", 5, exit_day=7),
        experiment_case("test", 7),
    )
    definition = active.define(
        source_revision="sha256:dataset",
        sessions=sessions(),
        cases=cases,
    )
    assignments = active.assignments(definition, active.folds(definition)[0], cases)
    by_case = {item.case_id: item for item in assignments}
    assert by_case[cases[0].case_id].partition is OptionExperimentPartition.TRAIN
    assert by_case[cases[1].case_id].partition is OptionExperimentPartition.EXCLUDED
    assert by_case[cases[1].case_id].reason == "LABEL_UNAVAILABLE_AT_CUTOFF"
    assert by_case[cases[2].case_id].partition is OptionExperimentPartition.TEST


def test_freeze_hash_rejects_test_evaluations_and_is_deterministic(tmp_path: Path) -> None:
    active = engine(small_config(tmp_path))
    cases = (experiment_case("train", 1), experiment_case("test", 7))
    definition = active.define(
        source_revision="sha256:dataset",
        sessions=sessions(),
        cases=cases,
    )
    fold = active.folds(definition)[0]
    train = active.evaluate_partition(definition, fold, OptionExperimentPartition.TRAIN, cases)
    validation = active.evaluate_partition(
        definition, fold, OptionExperimentPartition.VALIDATION, cases
    )
    first = active.frozen_definition_hash(definition, (fold,), (train, validation))
    second = active.frozen_definition_hash(definition, (fold,), (validation, train))
    assert first == second
    test = active.evaluate_partition(definition, fold, OptionExperimentPartition.TEST, cases)
    with pytest.raises(ValueError, match="test evaluations"):
        active.frozen_definition_hash(definition, (fold,), (train, test))


def test_partition_metrics_remain_case_level_and_disclosed(tmp_path: Path) -> None:
    active = engine(small_config(tmp_path, minimum_sample=2))
    cases = (experiment_case("train", 1), experiment_case("test", 7))
    definition = active.define(
        source_revision="sha256:dataset",
        sessions=sessions(),
        cases=cases,
    )
    result = active.evaluate_partition(
        definition,
        active.folds(definition)[0],
        OptionExperimentPartition.TEST,
        cases,
    )
    assert result.metrics.completed_count == 1
    assert not result.sample_sufficient
    assert "PARTITION_SAMPLE_BELOW_CONFIGURED_MINIMUM" in result.disclosures
    assert "CASE_LEVEL_METRICS_ONLY_NO_PORTFOLIO_CAPITAL_ALLOCATION" in result.disclosures
