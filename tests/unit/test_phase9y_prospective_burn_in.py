from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.cli.main import main
from trading_system.desktop.prospective_burn_in import (
    ProspectiveBurnInConfigError,
    ProspectiveBurnInObservation,
    ProspectiveBurnInPlan,
    ProspectiveBurnInState,
    build_prospective_burn_in_plan,
    evaluate_prospective_burn_in,
    load_prospective_burn_in_config,
    load_prospective_burn_in_observations,
)
from trading_system.desktop.release_audit import (
    ReleaseAuditAssessment,
    ReleaseAuditState,
    audit_release_readiness,
    load_release_audit_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9y.v1.yaml"
RELEASE_CONFIG = ROOT / "config/desktop.phase9x.v1.yaml"
HASH = "sha256:" + "a" * 64


def _request() -> dict[str, object]:
    return {
        "declared_at": "2026-09-12T12:00:00Z",
        "window_start": "2026-09-13T13:30:00Z",
        "window_end": "2026-09-15T20:00:00Z",
        "minimum_sessions": 2,
        "minimum_market_days": 2,
        "minimum_completed_trades": 2,
        "required_regimes": ["RANGE", "TREND"],
        "required_symbols": ["AAPL", "MSFT"],
        "required_timeframes": ["1H", "DAILY"],
        "required_strategy_categories": ["BREAKOUT", "RECLAIM"],
        "maximum_incidents": 0,
        "maximum_unmatched_reconciliations": 0,
        "maximum_stale_data_events": 0,
        "maximum_rejection_fraction": "0.10",
        "maximum_unresolved_recoveries": 0,
    }


def _release() -> ReleaseAuditAssessment:
    return audit_release_readiness(
        load_release_audit_config(RELEASE_CONFIG), project_root=ROOT
    )


def _plan() -> ProspectiveBurnInPlan:
    return build_prospective_burn_in_plan(
        load_prospective_burn_in_config(CONFIG), _release(), _request()
    )


def _rows() -> list[dict[str, object]]:
    return [
        {
            "session_id": "sandbox-001",
            "market_day": "2026-09-14",
            "observed_at": "2026-09-14T20:00:00Z",
            "regime": "RANGE",
            "symbols": ["AAPL"],
            "timeframes": ["1H"],
            "strategy_categories": ["RECLAIM"],
            "completed_trades": 1,
            "order_attempts": 1,
            "rejected_orders": 0,
            "incidents": 0,
            "unmatched_reconciliations": 0,
            "stale_data_events": 0,
            "unresolved_recoveries": 0,
            "evidence_hash": HASH,
            "environment": "WEBULL_SANDBOX",
        },
        {
            "session_id": "sandbox-002",
            "market_day": "2026-09-15",
            "observed_at": "2026-09-15T20:00:00Z",
            "regime": "TREND",
            "symbols": ["MSFT"],
            "timeframes": ["DAILY"],
            "strategy_categories": ["BREAKOUT"],
            "completed_trades": 1,
            "order_attempts": 1,
            "rejected_orders": 0,
            "incidents": 0,
            "unmatched_reconciliations": 0,
            "stale_data_events": 0,
            "unresolved_recoveries": 0,
            "evidence_hash": HASH,
            "environment": "WEBULL_SANDBOX",
        },
    ]


def _observations(
    tmp_path: Path, rows: list[dict[str, object]] | None = None
) -> tuple[ProspectiveBurnInObservation, ...]:
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps({"observations": _rows() if rows is None else rows}), encoding="utf-8"
    )
    return load_prospective_burn_in_observations(path)


def test_plan_requires_ready_release_and_has_no_authority() -> None:
    plan = _plan()
    assert not plan.execution_authorized
    assert not plan.network_authorized
    assert not plan.credential_loading_authorized
    assert not plan.production_release_authorized
    blocked = replace(
        _release(), state=ReleaseAuditState.BLOCKED, blockers=("TEST_BLOCKER",)
    )
    with pytest.raises(ValueError, match="ready Phase 9X"):
        build_prospective_burn_in_plan(
            load_prospective_burn_in_config(CONFIG), blocked, _request()
        )


def test_complete_coverage_passes_deterministically(tmp_path: Path) -> None:
    observations = _observations(tmp_path)
    first = evaluate_prospective_burn_in(
        _plan(), observations, evaluated_at=datetime(2026, 9, 15, 20, tzinfo=UTC)
    )
    second = evaluate_prospective_burn_in(
        _plan(), tuple(reversed(observations)), evaluated_at=first.evaluated_at
    )
    assert first == second
    assert first.state is ProspectiveBurnInState.PASS
    assert not first.reason_codes
    assert not first.production_release_authorized
    assert not first.broker_write_performed
    assert not first.file_write_performed
    assert not first.process_launched
    assert not first.credentials_loaded
    assert not first.network_used
    assert not first.sandbox_execution_performed


def test_open_or_incomplete_window_remains_in_progress(tmp_path: Path) -> None:
    assessment = evaluate_prospective_burn_in(
        _plan(),
        _observations(tmp_path, _rows()[:1]),
        evaluated_at=datetime(2026, 9, 14, 20, tzinfo=UTC),
    )
    assert assessment.state is ProspectiveBurnInState.IN_PROGRESS
    assert "WINDOW_OPEN" in assessment.reason_codes
    assert "INSUFFICIENT_SESSIONS" in assessment.reason_codes
    assert assessment.missing_symbols == ("MSFT",)


def test_tolerance_breach_fails_closed(tmp_path: Path) -> None:
    rows = _rows()
    rows[1]["incidents"] = 1
    assessment = evaluate_prospective_burn_in(
        _plan(),
        _observations(tmp_path, rows),
        evaluated_at=datetime(2026, 9, 15, 20, tzinfo=UTC),
    )
    assert assessment.state is ProspectiveBurnInState.FAIL
    assert "INCIDENT_LIMIT_EXCEEDED" in assessment.reason_codes


def test_non_sandbox_or_future_evidence_is_rejected(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["environment"] = "LIVE"
    with pytest.raises(ValueError, match="observation"):
        _observations(tmp_path, rows)
    observations = _observations(tmp_path, _rows())
    with pytest.raises(ValueError, match="causal plan window"):
        evaluate_prospective_burn_in(
            _plan(), observations, evaluated_at=datetime(2026, 9, 14, tzinfo=UTC)
        )


def test_config_rejects_defaults_and_execution_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["method"]["default_thresholds_enabled"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProspectiveBurnInConfigError, match="method"):
        load_prospective_burn_in_config(path)


def test_cli_builds_plan_and_evaluates_offline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.json"
    evidence = tmp_path / "evidence.json"
    request.write_text(json.dumps(_request()), encoding="utf-8")
    evidence.write_text(json.dumps({"observations": _rows()}), encoding="utf-8")
    common = [
        "--config",
        str(CONFIG),
        "--release-config",
        str(RELEASE_CONFIG),
        "--request",
        str(request),
        "--project-root",
        str(ROOT),
    ]
    assert main(["desktop", "burn-in-plan", *common]) == 0
    plan_payload = json.loads(capsys.readouterr().out)
    assert plan_payload["execution_authorized"] is False
    assert main(
        [
            "desktop",
            "burn-in-evaluate",
            *common,
            "--evidence",
            str(evidence),
            "--as-of",
            "2026-09-15T20:00:00Z",
        ]
    ) == 0
    assessment_payload = json.loads(capsys.readouterr().out)
    assert assessment_payload["state"] == "PASS"
    assert assessment_payload["production_release_authorized"] is False
