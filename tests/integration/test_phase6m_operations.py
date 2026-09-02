from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6m import CONFIG, seed_review_history

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6m_cli_export_verify_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = seed_review_history(repository)
    request = tmp_path / "bundle.json"
    request.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "source_verification_id": verification_id,
                "bundled_at": (AS_OF + timedelta(hours=16)).isoformat(),
                "source_revision": "sha256:cli-bundle",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "prospective-chain-review-bundle",
            "--config",
            str(CONFIG),
            "--input",
            str(request),
            "--database",
            str(database),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    bundle_id = output["evidence"]["bundle_id"]
    assert output["reviewers_authenticated"] is False
    verify = tmp_path / "verify.json"
    verify.write_text(
        json.dumps(
            {
                "bundle_id": bundle_id,
                "verified_at": (AS_OF + timedelta(hours=17)).isoformat(),
                "source_revision": "sha256:cli-verify",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "verify-prospective-chain-review-bundle",
            "--config",
            str(CONFIG),
            "--input",
            str(verify),
            "--database",
            str(database),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["status"] == "VERIFIED"
    assert main(
        [
            "operations",
            "prospective-chain-review-bundle-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--bundle-id",
            bundle_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)["evidence"]
    assert status["latest_verification_status"] == "VERIFIED"
    assert status["manifest"]["review_count"] == 2
