from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6o import CONFIG as CATALOG_PLAN_CONFIG
from tests.unit.test_phase6p import CONFIG as PLAN_CONFIG
from tests.unit.test_phase6q import CONFIG, seed_complete_plan

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6q_cli_materializes_bound_membership_and_reports_status(
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
                "source_plan_id": plan_id,
                "materialized_at": (AS_OF + timedelta(hours=19)).isoformat(),
                "cataloged_at": (AS_OF + timedelta(hours=20)).isoformat(),
                "source_revision": "sha256:phase6q-cli",
            }
        ),
        encoding="utf-8",
    )
    common = [
        "--config",
        str(CONFIG),
        "--plan-config",
        str(PLAN_CONFIG),
        "--catalog-plan-config",
        str(CATALOG_PLAN_CONFIG),
        "--catalog-config",
        str(CATALOG_CONFIG),
        "--database",
        str(database),
    ]
    assert (
        main(
            [
                "operations",
                "materialize-prospective-review-bundle-catalog",
                *common,
                "--input",
                str(request),
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    materialization = created["evidence"]["materialization"]
    assert created["evidence"]["inserted"] is True
    assert created["caller_membership_override_used"] is False
    assert created["consensus_calculated"] is False
    assert (
        main(
            [
                "operations",
                "prospective-review-bundle-materialization-status",
                *common,
                "--materialization-id",
                materialization["materialization_id"],
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["catalog_id"] == materialization["catalog_id"]
    assert status["production_readiness_claim"] is False


def test_phase6q_cli_validates_config(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "operations",
                "validate-prospective-review-bundle-materialization-config",
                "--config",
                str(CONFIG),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["evidence"]["valid"] is True
    assert output["live_trading_enabled"] is False
