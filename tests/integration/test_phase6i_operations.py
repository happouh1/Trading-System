from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6i import CONFIG

from trading_system.cli.main import main


def test_phase6i_cli_register_and_pending_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    request = tmp_path / "plan.json"
    request.write_text(
        json.dumps(
            {
                "catalog_name": "future-catalog",
                "registered_at": AS_OF.isoformat(),
                "slots": [
                    {
                        "slot_id": "window-2",
                        "expected_as_of": (AS_OF + timedelta(days=2)).isoformat(),
                    },
                    {
                        "slot_id": "window-1",
                        "expected_as_of": (AS_OF + timedelta(days=1)).isoformat(),
                    },
                ],
                "source_revision": "sha256:cli-plan",
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "operations",
                "register-prospective-review-plan",
                "--config",
                str(CONFIG),
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
    assert created["network_used"] is False
    assert (
        main(
            [
                "operations",
                "prospective-review-plan-status",
                "--config",
                str(CONFIG),
                "--database",
                str(database),
                "--plan-id",
                plan_id,
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["pending_count"] == 2
    assert status["evidence"]["complete"] is False
