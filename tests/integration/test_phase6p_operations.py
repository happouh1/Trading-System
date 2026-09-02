from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6p import CONFIG

from trading_system.cli.main import main


def test_phase6p_cli_register_and_pending_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database, request = tmp_path / "operations.sqlite", tmp_path / "plan.json"
    request.write_text(
        json.dumps(
            {
                "catalog_name": "future-review-catalog",
                "registered_at": AS_OF.isoformat(),
                "slots": [
                    {
                        "slot_id": "review-window-1",
                        "expected_as_of": (AS_OF + timedelta(days=1)).isoformat(),
                    }
                ],
                "source_revision": "sha256:phase6p-cli",
            }
        ),
        encoding="utf-8",
    )
    common = ["--config", str(CONFIG), "--catalog-config", str(CATALOG_CONFIG)]
    assert (
        main(
            [
                "operations",
                "register-prospective-review-bundle-plan",
                *common,
                "--input",
                str(request),
                "--database",
                str(database),
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    plan_id = created["evidence"]["plan"]["plan_id"]
    assert (
        main(
            [
                "operations",
                "prospective-review-bundle-plan-status",
                *common,
                "--database",
                str(database),
                "--plan-id",
                plan_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["pending_count"] == 1
    assert status["timing_compliance_claim"] is False
