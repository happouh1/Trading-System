from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6e import CONFIG, seed_verified_export

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6e_cli_review_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification = seed_verified_export(repository)
    review_input = tmp_path / "review.json"
    review_input.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "verification_id": verification.verification_id,
                "reviewer_id": "local-reviewer-assertion",
                "reviewed_at": (AS_OF + timedelta(hours=7)).isoformat(),
                "verdict": "UNCERTAIN",
                "reason_codes": ["INDEPENDENCE_NOT_AUTHENTICATED"],
                "notes": "Offline review only.",
                "supersedes_review_id": None,
                "source_revision": "sha256:cli-review",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "observation-audit-review",
            "--config",
            str(CONFIG),
            "--input",
            str(review_input),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["review"]["verdict"] == "UNCERTAIN"
    assert created["review"]["eligible_for_summary"] is False
    assert created["reviewer_authenticated"] is False
    assert created["consensus_calculated"] is False
    assert main(
        [
            "operations",
            "observation-audit-review-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--export-id",
            export_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["counts"]["TOTAL"] == 1
    assert status["counts"]["UNCERTAIN"] == 1
    assert status["counts"]["SUMMARY_ELIGIBLE"] == 0
    assert status["consensus_calculated"] is False
