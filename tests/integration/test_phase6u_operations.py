from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6u import ANSWERS, CONFIG, verified_review

from trading_system.cli.main import main
from trading_system.persistence import SQLiteRepository


def test_phase6u_cli_register_and_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
    request = tmp_path / "proposal.json"
    request.write_text(
        json.dumps(
            {
                "review_export_id": export_id,
                "review_verification_id": verification_id,
                "proposed_at": (AS_OF + timedelta(hours=27)).isoformat(),
                "source_revision": "sha256:phase6u-cli-proposal",
                **ANSWERS,
            }
        ),
        encoding="utf-8",
    )
    common = ["--config", str(CONFIG), "--review-config", str(REVIEW_CONFIG)]
    assert main(
        [
            "operations",
            "register-artifact-trust-policy-proposal",
            *common,
            "--input",
            str(request),
            "--database",
            str(database),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    proposal_id = output["evidence"]["proposal"]["proposal_id"]
    assert output["evidence"]["proposal"]["status"] == "PROPOSED_UNAUTHENTICATED"
    assert output["policy_activated"] is output["reviewers_authenticated"] is False
    assert main(
        [
            "operations",
            "artifact-trust-policy-proposal-status",
            *common,
            "--database",
            str(database),
            "--proposal-id",
            proposal_id,
        ]
    ) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["evidence"]["proposal_id"] == proposal_id
    assert status["automatic_promotion_performed"] is False


def test_phase6u_cli_validates_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(
        [
            "operations",
            "validate-artifact-trust-policy-proposal-config",
            "--config",
            str(CONFIG),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["evidence"]["valid"] is True
    assert output["network_used"] is output["live_trading_enabled"] is False
