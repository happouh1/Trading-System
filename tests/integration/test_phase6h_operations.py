from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6h import CONFIG, seed_plan_and_catalog

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6h_cli_plan_reconcile_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
    reconcile_input = tmp_path / "reconcile.json"
    reconcile_input.write_text(
        json.dumps(
            {
                "plan_id": plan_id,
                "catalog_id": catalog_id,
                "reconciled_at": (AS_OF + timedelta(hours=12)).isoformat(),
                "source_revision": "sha256:cli-reconcile",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "reconcile-review-catalog-plan",
            "--config",
            str(CONFIG),
            "--input",
            str(reconcile_input),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    reconciliation_id = str(created["evidence"]["reconciliation"]["reconciliation_id"])
    assert created["evidence"]["reconciliation"]["status"] == "MATCHED"
    assert created["selection_unbiased_claim"] is False
    assert main(
        [
            "operations",
            "review-catalog-reconciliation-status",
            "--config",
            str(CONFIG),
            "--database",
            str(database),
            "--reconciliation-id",
            reconciliation_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["status"] == "MATCHED"
    assert status["consensus_calculated"] is False
