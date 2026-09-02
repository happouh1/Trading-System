from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6n import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6n import seed_verified_bundle
from tests.unit.test_phase6o import CONFIG, seed_plan_and_catalog

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6o_cli_register_and_plan_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        bundle_id, verification_id = seed_verified_bundle(repository)
    request = tmp_path / "plan.json"
    request.write_text(
        json.dumps(
            {
                "catalog_name": "cli-planned-catalog",
                "registered_at": (AS_OF + timedelta(hours=17, minutes=30)).isoformat(),
                "sources": [
                    {"bundle_id": bundle_id, "verification_id": verification_id}
                ],
                "source_revision": "sha256:phase6o-cli-plan",
            }
        ),
        encoding="utf-8",
    )
    common = ["--config", str(CONFIG), "--catalog-config", str(CATALOG_CONFIG)]
    assert main(
        [
            "operations",
            "register-prospective-chain-review-catalog-plan",
            *common,
            "--input",
            str(request),
            "--database",
            str(database),
        ]
    ) == 0
    created = json.loads(capsys.readouterr().out)
    plan_id = created["evidence"]["plan"]["plan_id"]
    assert created["evidence"]["inserted"] is True
    assert main(
        [
            "operations",
            "prospective-chain-review-catalog-plan-status",
            *common,
            "--database",
            str(database),
            "--plan-id",
            plan_id,
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["catalog_name"] == (
        "cli-planned-catalog"
    )


def test_phase6o_cli_reconcile_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        plan_id, catalog_id = seed_plan_and_catalog(repository)
    request = tmp_path / "reconcile.json"
    request.write_text(
        json.dumps(
            {
                "plan_id": plan_id,
                "catalog_id": catalog_id,
                "reconciled_at": (AS_OF + timedelta(hours=19)).isoformat(),
                "source_revision": "sha256:phase6o-cli",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "reconcile-prospective-chain-review-catalog-plan",
            "--config",
            str(CONFIG),
            "--catalog-config",
            str(CATALOG_CONFIG),
            "--input",
            str(request),
            "--database",
            str(database),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    result = output["evidence"]["reconciliation"]
    assert result["status"] == "MATCHED"
    assert output["selection_unbiased_claim"] is False
    assert main(
        [
            "operations",
            "prospective-chain-review-catalog-reconciliation-status",
            "--config",
            str(CONFIG),
            "--catalog-config",
            str(CATALOG_CONFIG),
            "--database",
            str(database),
            "--reconciliation-id",
            result["reconciliation_id"],
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["status"] == "MATCHED"
