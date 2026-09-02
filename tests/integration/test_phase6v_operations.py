from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import CONFIG as PROPOSAL_CONFIG
from tests.unit.test_phase6v import CONFIG, proposals

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6v_cli_create_and_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
    request = tmp_path / "catalog.json"
    request.write_text(
        json.dumps(
            {
                "proposal_ids": proposal_ids,
                "cataloged_at": (AS_OF + timedelta(hours=29)).isoformat(),
                "source_revision": "sha256:phase6v-cli-catalog",
            }
        ),
        encoding="utf-8",
    )
    common = [
        "--config",
        str(CONFIG),
        "--proposal-config",
        str(PROPOSAL_CONFIG),
        "--review-config",
        str(REVIEW_CONFIG),
    ]
    assert (
        main(
            [
                "operations",
                "create-artifact-trust-proposal-catalog",
                *common,
                "--input",
                str(request),
                "--database",
                str(database),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    catalog_id = output["evidence"]["catalog"]["catalog_id"]
    assert output["proposal_selected"] is output["consensus_calculated"] is False
    assert (
        main(
            [
                "operations",
                "artifact-trust-proposal-catalog-status",
                *common,
                "--database",
                str(database),
                "--catalog-id",
                catalog_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["catalog_id"] == catalog_id
    assert status["policy_activated"] is False


def test_phase6v_cli_validates_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "operations",
                "validate-artifact-trust-proposal-catalog-config",
                "--config",
                str(CONFIG),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["evidence"]["valid"] is True
