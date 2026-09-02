from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG, seed_verified_bundle

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6n_cli_create_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
    request = tmp_path / "catalog.json"
    request.write_text(
        json.dumps(
            {
                "catalog_name": "prospective-review-wave-1",
                "cataloged_at": (AS_OF + timedelta(hours=18)).isoformat(),
                "sources": [
                    {"bundle_id": bundle_id, "verification_id": verification_id}
                ],
                "source_revision": "sha256:phase6n-cli",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "prospective-chain-review-catalog",
            "--config",
            str(CONFIG),
            "--input",
            str(request),
            "--database",
            str(database),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    catalog_id = output["evidence"]["catalog"]["catalog_id"]
    assert output["evidence"]["inserted"] is True
    assert output["caller_selection_used"] is True
    assert output["consensus_calculated"] is False
    assert main(
        [
            "operations",
            "prospective-chain-review-catalog-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--catalog-id",
            catalog_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["bundle_count"] == 1
    assert status["evidence"]["entries"][0]["bundle_id"] == bundle_id
