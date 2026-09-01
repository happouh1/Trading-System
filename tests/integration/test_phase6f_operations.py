from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6f import CONFIG, seed_review_history

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6f_cli_export_verify_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
    export_input = tmp_path / "bundle.json"
    export_input.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "source_verification_id": verification_id,
                "bundled_at": (AS_OF + timedelta(hours=9)).isoformat(),
                "source_revision": "sha256:cli-bundle",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "observation-audit-review-export",
            "--config",
            str(CONFIG),
            "--input",
            str(export_input),
            "--database",
            str(database),
        ]
    ) == 0
    exported = json.loads(capsys.readouterr().out)
    bundle_id = str(exported["evidence"]["bundle_id"])
    assert exported["consensus_calculated"] is False
    assert exported["reviewers_authenticated"] is False
    verify_input = tmp_path / "verify.json"
    verify_input.write_text(
        json.dumps(
            {
                "bundle_id": bundle_id,
                "verified_at": (AS_OF + timedelta(hours=10)).isoformat(),
                "source_revision": "sha256:cli-verify",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "verify-observation-audit-review-export",
            "--config",
            str(CONFIG),
            "--input",
            str(verify_input),
            "--database",
            str(database),
        ]
    ) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["evidence"]["status"] == "VERIFIED"
    assert main(
        [
            "operations",
            "observation-audit-review-export-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--bundle-id",
            bundle_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["latest_verification_status"] == "VERIFIED"
    assert status["verification_count"] == 1
    assert status["manifest"]["review_count"] == 2
