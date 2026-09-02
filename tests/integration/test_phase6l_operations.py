from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6l import CONFIG, seed_verified_chain

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6l_cli_review_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = seed_verified_chain(repository)
    request = tmp_path / "review.json"
    request.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "verification_id": verification_id,
                "reviewer_id": "asserted-local-reviewer",
                "reviewed_at": (AS_OF + timedelta(hours=14)).isoformat(),
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
            "prospective-chain-review",
            "--config",
            str(CONFIG),
            "--input",
            str(request),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["evidence"]["review"]["verdict"] == "UNCERTAIN"
    assert created["reviewer_authenticated"] is False
    assert created["consensus_calculated"] is False
    assert main(
        [
            "operations",
            "prospective-chain-review-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--export-id",
            export_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["counts"]["TOTAL"] == 1
    assert status["evidence"]["counts"]["UNCERTAIN"] == 1
    assert status["evidence"]["counts"]["SUMMARY_ELIGIBLE"] == 0
