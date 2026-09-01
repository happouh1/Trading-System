from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6d import CONFIG, seed_packet

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6d_cli_export_verify_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        packet_id = seed_packet(repository)
    export_input = tmp_path / "export.json"
    export_input.write_text(
        json.dumps(
            {
                "packet_id": packet_id,
                "exported_at": (AS_OF + timedelta(hours=5)).isoformat(),
                "source_revision": "sha256:cli-export",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "observation-audit-export",
            "--config",
            str(CONFIG),
            "--input",
            str(export_input),
            "--database",
            str(database),
        ]
    ) == 0
    exported = json.loads(capsys.readouterr().out)
    export_id = str(exported["evidence"]["export_id"])
    assert exported["network_used"] is False
    assert exported["external_signature_performed"] is False
    verify_input = tmp_path / "verify.json"
    verify_input.write_text(
        json.dumps(
            {
                "export_id": export_id,
                "verified_at": (AS_OF + timedelta(hours=6)).isoformat(),
                "source_revision": "sha256:cli-verify",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "verify-observation-audit-export",
            "--config",
            str(CONFIG),
            "--input",
            str(verify_input),
            "--database",
            str(database),
        ]
    ) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["evidence"]["status"] == "VERIFIED"
    assert main(
        [
            "operations",
            "observation-audit-export-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--export-id",
            export_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["latest_verification_status"] == "VERIFIED"
    assert status["verification_count"] == 1
    assert status["manifest"]["campaign_status"] == "INCOMPLETE"
