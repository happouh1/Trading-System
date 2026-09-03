from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import CONFIG as PROPOSAL_CONFIG
from tests.unit.test_phase6u import create_proposal, verified_review
from tests.unit.test_phase6u import registry as proposal_registry

from trading_system.cli import main
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6x.v1.yaml"


def test_phase6x_cli_register_bind_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
    plan_input = tmp_path / "plan.json"
    plan_input.write_text(json.dumps({
        "plan_name": "cli-prospective-plan",
        "review_export_id": export_id,
        "review_verification_id": verification_id,
        "registered_at": (AS_OF + timedelta(hours=26, minutes=30)).isoformat(),
        "slots": [{
            "slot_id": "slot-a",
            "opens_at": (AS_OF + timedelta(hours=27)).isoformat(),
            "closes_at": (AS_OF + timedelta(hours=28)).isoformat(),
        }],
        "source_revision": "sha256:phase6x-cli-plan",
    }), encoding="utf-8")
    common = [
        "--config", str(CONFIG),
        "--proposal-config", str(PROPOSAL_CONFIG),
        "--review-config", str(REVIEW_CONFIG),
        "--database", str(database),
    ]
    assert main([
        "operations", "register-artifact-trust-proposal-plan", *common,
        "--input", str(plan_input),
    ]) == 0
    plan_id = json.loads(capsys.readouterr().out)["evidence"]["plan"]["plan_id"]
    with SQLiteRepository(database) as repository:
        repository.migrate()
        proposal = create_proposal(
            proposal_registry(repository), export_id, verification_id,
            proposed_at=AS_OF + timedelta(hours=27, minutes=15),
        )
        assert proposal_registry(repository).insert(proposal)
    binding_input = tmp_path / "binding.json"
    binding_input.write_text(json.dumps({
        "plan_id": plan_id,
        "slot_id": "slot-a",
        "proposal_id": proposal.proposal_id,
        "bound_at": (AS_OF + timedelta(hours=27, minutes=30)).isoformat(),
        "source_revision": "sha256:phase6x-cli-binding",
    }), encoding="utf-8")
    assert main([
        "operations", "bind-artifact-trust-proposal-slot", *common,
        "--input", str(binding_input),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["inserted"] is True
    assert main([
        "operations", "artifact-trust-proposal-plan-status", *common,
        "--plan-id", plan_id,
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["evidence"]["complete"] is True
    assert output["complete_population_claim"] is False
    assert output["network_used"] is False
    assert output["broker_write_performed"] is False
