from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6g import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6i import CONFIG as PLAN_CONFIG
from tests.unit.test_phase6j import CONFIG as MATERIALIZATION_CONFIG
from tests.unit.test_phase6k import CONFIG, seed_materialization

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6k_cli_export_verify_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        materialization_id = seed_materialization(repository)
    common = [
        "--config",
        str(CONFIG),
        "--prospective-config",
        str(PLAN_CONFIG),
        "--catalog-config",
        str(CATALOG_CONFIG),
        "--materialization-config",
        str(MATERIALIZATION_CONFIG),
    ]
    request = tmp_path / "export.json"
    request.write_text(
        json.dumps(
            {
                "materialization_id": materialization_id,
                "exported_at": (AS_OF + timedelta(hours=12)).isoformat(),
                "source_revision": "sha256:cli-export",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "prospective-chain-export",
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
    verify = tmp_path / "verify.json"
    verify.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "verified_at": (AS_OF + timedelta(hours=13)).isoformat(),
                "source_revision": "sha256:cli-verify",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "verify-prospective-chain-export",
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
                "prospective-chain-export-status",
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
    assert json.loads(capsys.readouterr().out)["evidence"]["verification_count"] == 1
