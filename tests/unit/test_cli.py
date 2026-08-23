from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from trading_system.cli import main
from trading_system.persistence import SQLiteRepository
from trading_system.research.contracts import ExperimentSpec, WalkForwardFold, WalkForwardSpec
from trading_system.research.orchestration import CohortSpec
from trading_system.research.registry import ExperimentRegistry

ROOT = Path(__file__).parents[2]


def test_report_and_empty_export_commands(tmp_path: Path) -> None:
    database = tmp_path / "cli.sqlite"
    report = tmp_path / "report.md"
    export = tmp_path / "observations.csv"
    assert main(
        [
            "report",
            "--database",
            str(database),
            "--run-id",
            "run-1",
            "--output",
            str(report),
        ]
    ) == 0
    assert "survivorship bias" in report.read_text(encoding="utf-8")
    assert main(
        [
            "export-observations",
            "--database",
            str(database),
            "--run-id",
            "run-1",
            "--format",
            "csv",
            "--output",
            str(export),
        ]
    ) == 0
    assert export.read_text(encoding="utf-8") == ""


def test_explain_returns_nonzero_for_unknown_decision(tmp_path: Path) -> None:
    assert main(
        [
            "explain",
            "--database",
            str(tmp_path / "cli.sqlite"),
            "--decision-id",
            "missing",
        ]
    ) == 1


def test_replay_cli_persists_complete_causal_run(tmp_path: Path) -> None:
    database = tmp_path / "replay.sqlite"
    assert main(
        [
            "replay",
            "--input",
            str(ROOT / "tests/fixtures/xnys_one_session.csv"),
            "--database",
            str(database),
            "--run-id",
            "cli-replay-1",
            "--config",
            str(ROOT / "config/thresholds.phase1e.v1.yaml"),
        ]
    ) == 0
    with SQLiteRepository(database) as repository:
        repository.migrate()
        counts = repository.run_counts("cli-replay-1")
        checkpoint = repository.load_checkpoint("cli-replay-1")
    assert counts["candles"] == 7
    assert counts["feature_snapshots"] == 7
    assert counts["decisions"] == 7
    assert checkpoint is not None
    assert checkpoint[1] == 7


def test_research_cli_reports_and_advances_stage(tmp_path: Path) -> None:
    database = tmp_path / "research.sqlite"
    dataset = tmp_path / "research.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "row_id": "row-1",
                "observation_id": "observation-1",
                "symbol": "AAPL",
                "session_date": "2021-01-04",
                "label_available_at": "2021-01-05T00:00:00Z",
                "outcome_label": "SUCCESS",
                "net_r": "1.0",
                "features": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    experiment = ExperimentSpec(
        "experiment-cli",
        datetime(2026, 1, 1, tzinfo=UTC),
        ("run-1",),
        "code",
        ("config",),
        ("data",),
        ("calendar",),
        "universe",
        WalkForwardSpec(),
        "metrics",
        "similarity",
        7,
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        registry = ExperimentRegistry(repository)
        registry.insert_experiment(experiment)
        registry.insert_fold(
            WalkForwardFold(
                "fold-cli",
                experiment.experiment_id,
                0,
                date(2020, 1, 1),
                date(2021, 12, 31),
                date(2022, 1, 10),
                date(2022, 3, 31),
                date(2022, 4, 10),
                date(2022, 6, 30),
            )
        )
        registry.insert_cohort(CohortSpec("all-cli", experiment.experiment_id, "all"))
    assert main(
        [
            "research",
            "status",
            "--database",
            str(database),
            "--experiment-id",
            experiment.experiment_id,
        ]
    ) == 0
    assert main(
        [
            "research",
            "run",
            "--database",
            str(database),
            "--experiment-id",
            experiment.experiment_id,
            "--stage",
            "train",
            "--dataset",
            str(dataset),
        ]
    ) == 0
    assert main(
        [
            "research",
            "run",
            "--database",
            str(database),
            "--experiment-id",
            experiment.experiment_id,
            "--stage",
            "validation",
            "--dataset",
            str(dataset),
        ]
    ) == 0
    assert main(
        [
            "research",
            "freeze",
            "--database",
            str(database),
            "--experiment-id",
            experiment.experiment_id,
            "--definition-hash",
            "sha256:frozen",
        ]
    ) == 0
    assert main(
        [
            "research",
            "run",
            "--database",
            str(database),
            "--experiment-id",
            experiment.experiment_id,
            "--stage",
            "test",
            "--dataset",
            str(dataset),
        ]
    ) == 0
    assert main(
        [
            "research",
            "complete",
            "--database",
            str(database),
            "--experiment-id",
            experiment.experiment_id,
        ]
    ) == 0
