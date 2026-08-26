from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.unit.test_phase3d_smoke import SMOKE_CONFIG, capture_payload, write_json

from trading_system.cli import main
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.webull.smoke import load_smoke_capture, load_smoke_config
from trading_system.webull.smoke_registry import WebullSmokeRegistry

ROOT = Path(__file__).parents[2]
WEBULL_CONFIG = ROOT / "config/webull.sandbox.v1.yaml"


def seed_session(database: Path) -> None:
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(
            PaperSession(
                "smoke-session", datetime(2026, 1, 5, tzinfo=UTC), PaperMode.SHADOW,
                "git:test", "config", "data", "XNYS",
            )
        )


def test_capture_review_restart_and_status_are_append_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "smoke.sqlite"
    capture_path = tmp_path / "capture.json"
    review_path = tmp_path / "review.json"
    seed_session(database)
    write_json(capture_path, capture_payload())
    capture = load_smoke_capture(capture_path, load_smoke_config(SMOKE_CONFIG))

    assert main([
        "webull", "import-smoke-capture", "--database", str(database),
        "--session-id", "smoke-session", "--config", str(WEBULL_CONFIG),
        "--smoke-config", str(SMOKE_CONFIG), "--capture", str(capture_path),
    ]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["capture_id"] == capture.capture_id
    assert imported["review_status"] == "PENDING_REVIEW"
    assert imported["broker_write_performed"] is False

    write_json(review_path, {
        "review_version": "3D-SMOKE-REVIEW.1.0",
        "capture_id": capture.capture_id,
        "reviewed_at": "2026-01-06T12:00:00Z",
        "reviewer_id": "operator-reviewer",
        "verdict": "PASS",
        "reason_codes": ["SCHEMA_MATCHED_CAPTURE"],
        "notes": "Disposable sandbox evidence reviewed.",
    })
    assert main([
        "webull", "import-smoke-review", "--database", str(database),
        "--session-id", "smoke-session", "--config", str(WEBULL_CONFIG),
        "--capture-id", capture.capture_id, "--review", str(review_path),
    ]) == 0
    review = json.loads(capsys.readouterr().out)
    assert review["verdict"] == "PASS"
    assert review["automatic_manifest_promotion"] is False

    with SQLiteRepository(database) as repository:
        repository.migrate()
        restarted = WebullSmokeRegistry(repository)
        assert restarted.capture(capture.capture_id) == capture
        assert restarted.passed_cases("smoke-session") == (capture.case,)
        assert restarted.insert_capture(capture) is False

    assert main([
        "webull", "smoke-status", "--database", str(database),
        "--session-id", "smoke-session", "--config", str(WEBULL_CONFIG),
        "--smoke-config", str(SMOKE_CONFIG),
    ]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["all_cases_passed"] is False
    assert status["official_exit_transport_enabled"] is False
    assert status["automatic_manifest_promotion"] is False


def test_smoke_plan_cli_performs_no_network_or_broker_write(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([
        "webull", "smoke-plan", "--config", str(WEBULL_CONFIG),
        "--smoke-config", str(SMOKE_CONFIG),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["cases"]) == 7
    assert payload["network_used"] is False
    assert payload["broker_write_performed"] is False
