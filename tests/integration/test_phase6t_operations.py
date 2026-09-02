from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6r import CONFIG as PHASE6R_CONFIG
from tests.unit.test_phase6s import CONFIG as PHASE6S_CONFIG
from tests.unit.test_phase6t import CONFIG, signing_request

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6t_cli_export_verify_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        request_id = signing_request(repository)
    common = [
        "--config",
        str(CONFIG),
        "--trust-config",
        str(PHASE6S_CONFIG),
        "--phase6r-config",
        str(PHASE6R_CONFIG),
    ]
    export_input = tmp_path / "export.json"
    export_input.write_text(
        json.dumps(
            {
                "signing_request_id": request_id,
                "exported_at": (AS_OF + timedelta(hours=25)).isoformat(),
                "source_revision": "sha256:phase6t-cli-export",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "artifact-trust-review-export",
            *common,
            "--input",
            str(export_input),
            "--database",
            str(database),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    export_id = output["evidence"]["export_id"]
    assert output["signed"] is output["reviewers_authenticated"] is False
    verify_input = tmp_path / "verify.json"
    verify_input.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "verified_at": (AS_OF + timedelta(hours=26)).isoformat(),
                "source_revision": "sha256:phase6t-cli-verify",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "verify-artifact-trust-review-export",
            *common,
            "--input",
            str(verify_input),
            "--database",
            str(database),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["status"] == "VERIFIED"
    assert main(
        [
            "operations",
            "artifact-trust-review-export-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--export-id",
            export_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["verification_count"] == 1
    assert status["automatic_promotion_performed"] is False


def test_phase6t_cli_validates_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(
        [
            "operations",
            "validate-artifact-trust-review-export-config",
            "--config",
            str(CONFIG),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["evidence"]["valid"] is True
    assert output["network_used"] is output["live_trading_enabled"] is False
