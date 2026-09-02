from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6g import CONFIG, seed_verified_bundle

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6g_cli_catalog_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification = seed_verified_bundle(repository)
    input_path = tmp_path / "catalog.json"
    input_path.write_text(
        json.dumps(
            {
                "catalog_name": "cli-explicit-catalog",
                "cataloged_at": (AS_OF + timedelta(hours=11)).isoformat(),
                "sources": [
                    {
                        "bundle_id": bundle_id,
                        "verification_id": verification.verification_id,
                    }
                ],
                "source_revision": "sha256:cli-catalog",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "observation-audit-review-catalog",
            "--config",
            str(CONFIG),
            "--input",
            str(input_path),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    catalog_id = str(created["catalog"]["catalog_id"])
    assert created["catalog"]["bundle_count"] == 1
    assert created["consensus_calculated"] is False
    assert created["ranking_calculated"] is False
    assert main(
        [
            "operations",
            "observation-audit-review-catalog-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--catalog-id",
            catalog_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["catalog"]["total_review_count"] == 2
    assert status["reviewers_authenticated"] is False
