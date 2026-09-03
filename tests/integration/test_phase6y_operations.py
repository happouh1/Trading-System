from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import CONFIG as PROPOSAL_CONFIG
from tests.unit.test_phase6v import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6x import CONFIG as PLAN_CONFIG
from tests.unit.test_phase6y import complete_plan

from trading_system.cli import main
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6y.v1.yaml"


def test_phase6y_cli_materializes_and_reads_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id = complete_plan(repository)
    materialization_input = tmp_path / "materialization.json"
    materialization_input.write_text(
        json.dumps(
            {
                "source_plan_id": plan_id,
                "materialized_at": (AS_OF + timedelta(hours=28)).isoformat(),
                "cataloged_at": (AS_OF + timedelta(hours=29)).isoformat(),
                "source_revision": "sha256:phase6y-cli",
            }
        ),
        encoding="utf-8",
    )
    common = [
        "--config",
        str(CONFIG),
        "--plan-config",
        str(PLAN_CONFIG),
        "--proposal-config",
        str(PROPOSAL_CONFIG),
        "--review-config",
        str(REVIEW_CONFIG),
        "--catalog-config",
        str(CATALOG_CONFIG),
        "--database",
        str(database),
    ]
    assert main(
        [
            "operations",
            "materialize-artifact-trust-proposal-catalog",
            *common,
            "--input",
            str(materialization_input),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    materialization_id = output["evidence"]["materialization"]["materialization_id"]
    assert output["evidence"]["inserted"] is True
    assert output["complete_population_claim"] is False
    assert output["network_used"] is False
    assert output["broker_write_performed"] is False
    assert main(
        [
            "operations",
            "artifact-trust-proposal-materialization-status",
            *common,
            "--materialization-id",
            materialization_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["materialization_id"] == materialization_id
    assert status["complete_population_claim"] is False
