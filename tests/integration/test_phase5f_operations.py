from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.test_phase5f import seed_release_chain

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase5f.v1.yaml"


def test_phase5f_cli_builds_and_reads_complete_offline_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        seed_release_chain(repository)
    input_path = tmp_path / "release-input.json"
    input_path.write_text(
        json.dumps(
            {
                "as_of": datetime(2026, 8, 30, 16, tzinfo=UTC).isoformat(),
                "readiness_manifest_id": "manifest-1",
                "monitor_report_id": "monitor-1",
                "control_snapshot_id": "control-1",
                "run_request_id": "request-1",
                "backup_id": "backup-1",
                "restore_verification_id": "restore-1",
                "source_revision": "sha256:release-source",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "release-evidence",
            "--config",
            str(CONFIG),
            "--input",
            str(input_path),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["bundle"]["status"] == "COMPLETE"
    assert created["inserted"] is True
    assert created["production_readiness_claim"] is False
    assert created["network_used"] is False
    bundle_id = str(created["bundle"]["bundle_id"])
    assert main(
        [
            "operations",
            "release-status",
            "--database",
            str(database),
            "--bundle-id",
            bundle_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "COMPLETE"
    assert status["production_readiness_claim"] is False
    assert status["broker_write_performed"] is False
