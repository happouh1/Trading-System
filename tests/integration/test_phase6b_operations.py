from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6b import CONFIG, create_campaign

from trading_system.cli.main import main
from trading_system.operations import CampaignWindowRequest
from trading_system.persistence import SQLiteRepository


def test_phase6b_cli_registers_reconciles_and_reads_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    plan_input = tmp_path / "plan.json"
    plan_input.write_text(
        json.dumps(
            {
                "campaign_name": "offline-shadow-observation",
                "registered_at": (AS_OF - timedelta(days=1)).isoformat(),
                "start_at": AS_OF.isoformat(),
                "end_at": (AS_OF + timedelta(hours=1)).isoformat(),
                "windows": [
                    {
                        "window_id": "window-2",
                        "expected_as_of": (AS_OF + timedelta(hours=1)).isoformat(),
                    },
                    {"window_id": "window-1", "expected_as_of": AS_OF.isoformat()},
                ],
                "source_revision": "sha256:cli-plan",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "register-observation-plan",
            "--config",
            str(CONFIG),
            "--input",
            str(plan_input),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    plan_id = str(created["plan"]["plan_id"])
    assert created["inserted"] is True
    assert main(
        [
            "operations",
            "observation-plan-status",
            "--database",
            str(database),
            "--plan-id",
            plan_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "REGISTERED"
    assert status["window_count"] == 2

    with SQLiteRepository(database) as repository:
        repository.migrate()
        report = create_campaign(
            repository,
            (
                CampaignWindowRequest("window-1", AS_OF, None),
                CampaignWindowRequest("window-2", AS_OF + timedelta(hours=1), None),
            ),
        )
    reconcile_input = tmp_path / "reconcile.json"
    reconcile_input.write_text(
        json.dumps(
            {
                "plan_id": plan_id,
                "campaign_report_id": report.report_id,
                "reconciled_at": (AS_OF + timedelta(hours=3)).isoformat(),
                "source_revision": "sha256:cli-reconciliation",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "reconcile-observation-plan",
            "--config",
            str(CONFIG),
            "--input",
            str(reconcile_input),
            "--database",
            str(database),
        ]
    ) == 0
    reconciled = json.loads(capsys.readouterr().out)
    assert reconciled["reconciliation"]["status"] == "MATCHED"
    assert reconciled["reconciliation"]["campaign_status"] == "INCOMPLETE"
    assert reconciled["network_used"] is False
    assert reconciled["broker_write_performed"] is False
