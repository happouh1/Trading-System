from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6g import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6i import CONFIG as PLAN_CONFIG
from tests.unit.test_phase6j import CONFIG, seed_complete_plan

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6j_cli_materialize_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id = seed_complete_plan(repository)
    request = tmp_path / "materialize.json"
    request.write_text(
        json.dumps(
            {
                "plan_id": plan_id,
                "materialized_at": (AS_OF + timedelta(hours=11)).isoformat(),
                "source_revision": "sha256:cli-materialization",
            }
        ),
        encoding="utf-8",
    )
    common = [
        "--config",
        str(CONFIG),
        "--prospective-config",
        str(PLAN_CONFIG),
        "--catalog-config",
        str(CATALOG_CONFIG),
    ]
    assert (
        main(
            [
                "operations",
                "materialize-prospective-review-catalog",
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
    materialization_id = output["evidence"]["materialization"]["materialization_id"]
    assert output["caller_membership_override_used"] is False
    assert (
        main(
            [
                "operations",
                "prospective-catalog-materialization-status",
                *common,
                "--database",
                str(database),
                "--materialization-id",
                materialization_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["plan_id"] == plan_id
