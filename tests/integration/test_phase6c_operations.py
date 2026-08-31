from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6c import CONFIG, seed_reconciliation

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6c_cli_creates_and_reads_audit_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        _, _, reconciliation = seed_reconciliation(repository)
    input_path = tmp_path / "audit.json"
    input_path.write_text(
        json.dumps(
            {
                "reconciliation_id": reconciliation.reconciliation_id,
                "created_at": (AS_OF + timedelta(hours=4)).isoformat(),
                "source_revision": "sha256:cli-audit",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "observation-audit-packet",
            "--config",
            str(CONFIG),
            "--input",
            str(input_path),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["packet"]["status"] == "COMPLETE"
    assert created["packet"]["campaign_status"] == "INCOMPLETE"
    assert created["external_attestation_performed"] is False
    packet_id = str(created["packet"]["packet_id"])
    assert main(
        [
            "operations",
            "observation-audit-status",
            "--database",
            str(database),
            "--packet-id",
            packet_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "COMPLETE"
    assert status["artifact_count"] == 7
    assert status["network_used"] is False
    assert status["broker_write_performed"] is False
