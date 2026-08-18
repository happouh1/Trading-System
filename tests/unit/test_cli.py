from __future__ import annotations

from pathlib import Path

from trading_system.cli import main
from trading_system.persistence import SQLiteRepository

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
