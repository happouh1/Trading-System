from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import CONFIG as PROPOSAL_CONFIG
from tests.unit.test_phase6v import CONFIG as CATALOG_CONFIG
from tests.unit.test_phase6v import catalog_registry, proposals
from tests.unit.test_phase6w import CONFIG

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6w_cli_register_reconcile_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        proposal_ids = proposals(repository)
    common = [
        "--config", str(CONFIG),
        "--catalog-config", str(CATALOG_CONFIG),
        "--proposal-config", str(PROPOSAL_CONFIG),
        "--review-config", str(REVIEW_CONFIG),
    ]
    request = tmp_path / "plan.json"
    request.write_text(json.dumps({
        "proposal_ids": proposal_ids,
        "registered_at": (AS_OF + timedelta(hours=29)).isoformat(),
        "source_revision": "sha256:phase6w-cli-plan",
    }), encoding="utf-8")
    assert main(["operations", "register-artifact-trust-proposal-catalog-plan", *common,
                 "--input", str(request), "--database", str(database)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["selection_unbiased_claim"] is False
    plan_id = output["evidence"]["plan"]["plan_id"]
    with SQLiteRepository(database) as repository:
        repository.migrate()
        item = catalog_registry(repository).create(
            proposal_ids=proposal_ids,
            cataloged_at=AS_OF + timedelta(hours=30),
            source_revision="sha256:phase6w-cli-catalog",
        )
        assert catalog_registry(repository).insert(item)
        catalog_id = item.catalog_id
    reconcile = tmp_path / "reconcile.json"
    reconcile.write_text(json.dumps({
        "plan_id": plan_id,
        "catalog_id": catalog_id,
        "reconciled_at": (AS_OF + timedelta(hours=31)).isoformat(),
        "source_revision": "sha256:phase6w-cli-reconciliation",
    }), encoding="utf-8")
    assert main(["operations", "reconcile-artifact-trust-proposal-catalog-plan", *common,
                 "--input", str(reconcile), "--database", str(database)]) == 0
    result = json.loads(capsys.readouterr().out)["evidence"]["reconciliation"]
    assert result["status"] == "MATCHED"
    assert main(["operations", "artifact-trust-proposal-catalog-reconciliation-status",
                 *common, "--database", str(database),
                 "--reconciliation-id", result["reconciliation_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["status"] == "MATCHED"


def test_phase6w_cli_validates_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["operations", "validate-artifact-trust-proposal-catalog-plan-config",
                 "--config", str(CONFIG)]) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["valid"] is True
