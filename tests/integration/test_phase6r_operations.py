from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6o import CONFIG as CATALOG_PLAN_CONFIG
from tests.unit.test_phase6p import CONFIG as PLAN_CONFIG
from tests.unit.test_phase6q import CONFIG as MATERIALIZATION_CONFIG
from tests.unit.test_phase6r import CONFIG, seed_materialization

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6r_cli_export_verify_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        materialization_id = seed_materialization(repository)
    common = [
        "--config",
        str(CONFIG),
        "--materialization-config",
        str(MATERIALIZATION_CONFIG),
        "--plan-config",
        str(PLAN_CONFIG),
        "--catalog-plan-config",
        str(CATALOG_PLAN_CONFIG),
        "--catalog-config",
        str(CATALOG_CONFIG),
    ]
    request = tmp_path / "export.json"
    request.write_text(
        json.dumps(
            {
                "materialization_id": materialization_id,
                "exported_at": (AS_OF + timedelta(hours=21)).isoformat(),
                "source_revision": "sha256:phase6r-cli-export",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "prospective-review-bundle-chain-export",
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
    export_id = output["evidence"]["export_id"]
    assert output["signed"] is False
    verify = tmp_path / "verify.json"
    verify.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "verified_at": (AS_OF + timedelta(hours=22)).isoformat(),
                "source_revision": "sha256:phase6r-cli-verify",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "verify-prospective-review-bundle-chain-export",
                *common,
                "--input",
                str(verify),
                "--database",
                str(database),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["evidence"]["status"] == "VERIFIED"
    assert (
        main(
            [
                "operations",
                "prospective-review-bundle-chain-export-status",
                "--config",
                str(CONFIG),
                "--database",
                str(database),
                "--export-id",
                export_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["verification_count"] == 1
    assert status["production_readiness_claim"] is False


def test_phase6r_cli_validates_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "operations",
                "validate-prospective-review-bundle-chain-export-config",
                "--config",
                str(CONFIG),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["evidence"]["valid"] is True
    assert output["live_trading_enabled"] is False
