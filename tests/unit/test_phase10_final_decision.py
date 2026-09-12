from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.unit.test_phase9y_prospective_burn_in import (
    _observations,
    _plan,
    _rows,
)
from tests.unit.test_phase9y_prospective_burn_in import (
    _request as burn_in_request,
)
from trading_system.cli.main import main
from trading_system.desktop.final_decision import (
    FinalDecisionConfigError,
    FinalDecisionState,
    build_final_decision_request,
    evaluate_final_decision,
    load_final_decision_config,
)
from trading_system.desktop.prospective_burn_in import (
    ProspectiveBurnInAssessment,
    evaluate_prospective_burn_in,
)
from trading_system.desktop.release_audit import (
    ReleaseAuditAssessment,
    audit_release_readiness,
    load_release_audit_config,
)

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase10.v1.yaml"
RELEASE_CONFIG = ROOT / "config/desktop.phase9x.v1.yaml"
BURN_CONFIG = ROOT / "config/desktop.phase9y.v1.yaml"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
AS_OF = datetime(2026, 9, 16, 12, tzinfo=UTC)


def _release() -> ReleaseAuditAssessment:
    return audit_release_readiness(
        load_release_audit_config(RELEASE_CONFIG), project_root=ROOT
    )


def _request(target: str = "SUPERVISED_PAPER_ONLY") -> dict[str, object]:
    return {
        "requested_at": "2026-09-16T11:00:00Z",
        "target": target,
        "reviewer_identities": ["independent-risk-reviewer", "system-operator"],
        "capital_policy_hash": HASH_A,
        "risk_policy_hash": HASH_B,
        "evidence_retention_hash": HASH_C,
        "acknowledgement": "LIVE_TRADING_NOT_AUTHORIZED",
    }


def _passing_burn_in(tmp_path: Path) -> ProspectiveBurnInAssessment:
    return evaluate_prospective_burn_in(
        _plan(),
        _observations(tmp_path),
        evaluated_at=datetime(2026, 9, 15, 20, tzinfo=UTC),
    )


def test_current_status_is_blocked_pending_burn_in_and_request() -> None:
    assessment = evaluate_final_decision(
        load_final_decision_config(CONFIG), _release(), evaluated_at=AS_OF
    )
    assert assessment.state is FinalDecisionState.BLOCKED
    assert assessment.reason_codes == (
        "DECISION_REQUEST_MISSING",
        "PHASE9Y_EVIDENCE_MISSING",
    )
    assert not assessment.production_deployment_authorized
    assert not assessment.live_trading_authorized


@pytest.mark.parametrize(
    ("target", "state"),
    [
        ("RESEARCH_ONLY", FinalDecisionState.RESEARCH_ONLY_RECOMMENDED),
        ("SUPERVISED_PAPER_ONLY", FinalDecisionState.SUPERVISED_PAPER_ELIGIBLE),
        (
            "LIVE_AUTHORIZATION_REVIEW_ONLY",
            FinalDecisionState.SEPARATE_LIVE_AUTHORIZATION_REVIEW_ELIGIBLE,
        ),
    ],
)
def test_passing_evidence_classifies_target_without_authority(
    tmp_path: Path, target: str, state: FinalDecisionState
) -> None:
    config = load_final_decision_config(CONFIG)
    request = build_final_decision_request(config, _request(target))
    first = evaluate_final_decision(
        config,
        _release(),
        evaluated_at=AS_OF,
        burn_in=_passing_burn_in(tmp_path),
        request=request,
    )
    second = evaluate_final_decision(
        config,
        _release(),
        evaluated_at=AS_OF,
        burn_in=_passing_burn_in(tmp_path),
        request=request,
    )
    assert first == second
    assert first.state is state
    assert not first.production_deployment_authorized
    assert not first.live_trading_authorized
    assert not first.network_used
    assert not first.broker_write_performed


def test_incomplete_burn_in_blocks_final_decision(tmp_path: Path) -> None:
    burn_in = evaluate_prospective_burn_in(
        _plan(),
        _observations(tmp_path, _rows()[:1]),
        evaluated_at=datetime(2026, 9, 14, 20, tzinfo=UTC),
    )
    config = load_final_decision_config(CONFIG)
    assessment = evaluate_final_decision(
        config,
        _release(),
        evaluated_at=AS_OF,
        burn_in=burn_in,
        request=build_final_decision_request(config, _request()),
    )
    assert assessment.state is FinalDecisionState.BLOCKED
    assert assessment.reason_codes == ("PHASE9Y_NOT_PASS",)


def test_request_requires_independent_reviewers_and_acknowledgement() -> None:
    config = load_final_decision_config(CONFIG)
    request = _request()
    request["reviewer_identities"] = ["same-reviewer", "same-reviewer"]
    with pytest.raises(ValueError, match="reviewers"):
        build_final_decision_request(config, request)
    request = _request()
    request["acknowledgement"] = "ENABLE_LIVE"
    with pytest.raises(ValueError, match="request"):
        build_final_decision_request(config, request)


def test_config_rejects_deployment_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["production_deployment_enabled"] = True
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(FinalDecisionConfigError, match="authority"):
        load_final_decision_config(path)


def test_current_status_cli_is_canonical_and_blocked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(
        [
            "desktop",
            "final-decision-status",
            "--config",
            str(CONFIG),
            "--release-config",
            str(RELEASE_CONFIG),
            "--project-root",
            str(ROOT),
            "--as-of",
            "2026-09-16T12:00:00Z",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "BLOCKED"
    assert payload["production_deployment_authorized"] is False
    assert payload["live_trading_authorized"] is False


def test_full_cli_can_recommend_supervised_paper_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    burn_request_path = tmp_path / "burn-request.json"
    evidence_path = tmp_path / "evidence.json"
    request_path = tmp_path / "decision-request.json"
    burn_request_path.write_text(json.dumps(burn_in_request()), encoding="utf-8")
    evidence_path.write_text(json.dumps({"observations": _rows()}), encoding="utf-8")
    request_path.write_text(json.dumps(_request()), encoding="utf-8")
    assert main(
        [
            "desktop",
            "final-decision",
            "--config",
            str(CONFIG),
            "--release-config",
            str(RELEASE_CONFIG),
            "--burn-in-config",
            str(BURN_CONFIG),
            "--burn-in-request",
            str(burn_request_path),
            "--burn-in-evidence",
            str(evidence_path),
            "--request",
            str(request_path),
            "--project-root",
            str(ROOT),
            "--as-of",
            "2026-09-16T12:00:00Z",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "SUPERVISED_PAPER_ELIGIBLE"
    assert payload["production_deployment_authorized"] is False
