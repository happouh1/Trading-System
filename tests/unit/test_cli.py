from __future__ import annotations

from pathlib import Path

from trading_system.cli import main


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
