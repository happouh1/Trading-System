from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF, seed_release_bundles

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6a.v1.yaml"


def test_phase6a_cli_creates_and_reads_complete_campaign(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_ids = seed_release_bundles(repository)
    input_path = tmp_path / "campaign.json"
    input_path.write_text(
        json.dumps(
            {
                "campaign_name": "offline-shadow-observation",
                "start_at": AS_OF.isoformat(),
                "end_at": (AS_OF + timedelta(hours=1)).isoformat(),
                "evaluated_at": (AS_OF + timedelta(hours=2)).isoformat(),
                "windows": [
                    {
                        "window_id": "window-2",
                        "expected_as_of": (AS_OF + timedelta(hours=1)).isoformat(),
                        "bundle_id": bundle_ids[1],
                    },
                    {
                        "window_id": "window-1",
                        "expected_as_of": AS_OF.isoformat(),
                        "bundle_id": bundle_ids[0],
                    },
                ],
                "source_revision": "sha256:campaign-source",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "shadow-campaign",
            "--config",
            str(CONFIG),
            "--input",
            str(input_path),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["report"]["status"] == "COMPLETE"
    assert created["inserted"] is True
    assert created["production_readiness_claim"] is False
    assert created["automatic_promotion_performed"] is False
    report_id = str(created["report"]["report_id"])
    assert main(
        [
            "operations",
            "campaign-status",
            "--database",
            str(database),
            "--report-id",
            report_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "COMPLETE"
    assert status["window_count"] == 2
    assert status["network_used"] is False
    assert status["broker_write_performed"] is False


def test_phase6a_cli_rejects_naive_campaign_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "campaign.json"
    input_path.write_text(
        json.dumps(
            {
                "campaign_name": "invalid",
                "start_at": datetime(2026, 8, 30, 16).isoformat(),
                "end_at": datetime(2026, 8, 30, 17, tzinfo=UTC).isoformat(),
                "evaluated_at": datetime(2026, 8, 30, 18, tzinfo=UTC).isoformat(),
                "windows": [
                    {
                        "window_id": "window-1",
                        "expected_as_of": AS_OF.isoformat(),
                        "bundle_id": None,
                    }
                ],
                "source_revision": "sha256:invalid",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        main(
            [
                "operations",
                "shadow-campaign",
                "--config",
                str(CONFIG),
                "--input",
                str(input_path),
                "--database",
                str(tmp_path / "operations.sqlite"),
            ]
        )
    assert capsys.readouterr().out == ""
