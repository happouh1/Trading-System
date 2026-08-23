from __future__ import annotations

from pathlib import Path

from trading_system.cli import main

ROOT = Path(__file__).parents[2]


def test_shadow_cli_lifecycle_and_report(tmp_path: Path) -> None:
    database = tmp_path / "paper.sqlite"
    report = tmp_path / "paper.md"
    common = ["--database", str(database), "--session-id", "paper-cli"]
    assert main([
        "paper", "start", *common, "--config", str(ROOT / "config/paper.phase3b.v1.yaml"),
        "--data-revision", "fixture-v1", "--calendar-version", "XNYS-test",
    ]) == 0
    assert main(["paper", "status", *common]) == 0
    assert main([
        "paper", "resume", *common,
        "--config", str(ROOT / "config/paper.phase3b.v1.yaml"),
        "--data-revision", "fixture-v1", "--calendar-version", "XNYS-test",
    ]) == 0
    assert main(["paper", "report", *common, "--output", str(report)]) == 0
    body = report.read_text(encoding="utf-8")
    assert "external broker: `NONE`" in body
    assert "PHASE_1_RULES_ONLY" in body
    assert main(["paper", "drain", *common]) == 0
