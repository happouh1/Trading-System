from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_system.cli import main
from trading_system.desktop import (
    LocalOperationsStatus,
    assess_local_launch_readiness,
    load_launch_readiness_config,
)
from trading_system.desktop.readiness import LaunchReadinessConfigError
from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config/desktop.phase9j.v1.yaml"


def _operations(session_id: str | None = "paper-local-001") -> LocalOperationsStatus:
    values = (session_id, "AVAILABLE", "sha256:source", "sha256:config")
    return LocalOperationsStatus(
        "local_status_fixture",
        "AVAILABLE",
        session_id,
        "2026-09-10T14:00:00Z" if session_id else None,
        "SHADOW" if session_id else "UNKNOWN",
        "HEALTHY" if session_id else "UNAVAILABLE",
        "2026-09-10T14:01:00Z" if session_id else None,
        0,
        0,
        0,
        None,
        None,
        (),
        canonical_hash(values),
        "sha256:config",
    )


def _copy_status_config(root: Path) -> None:
    target = root / "config/desktop.phase9i.v1.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((ROOT / "config/desktop.phase9i.v1.yaml").read_bytes())


def _evidence_database(path: Path, *, complete: bool = True, tampered: bool = False) -> None:
    payload = {"fixture": "phase9j"}
    payload_json = canonical_json(payload)
    payload_hash = "sha256:tampered" if tampered else canonical_hash(payload)
    states = {
        "burn": "PASS",
        "cert": "REVIEW_READY" if complete else "INCOMPLETE",
        "rollout": "READY_FOR_HUMAN_REVIEW",
        "review": "SIGNATURES_VERIFIED",
        "lease": "SUPERVISION_WINDOW_OPEN",
    }
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE paper_burn_in_assessments (
                assessment_id TEXT, session_id TEXT, evaluated_at TEXT, state TEXT,
                payload_json TEXT, payload_hash TEXT);
            CREATE TABLE paper_certification_dossiers (dossier_id TEXT, session_id TEXT);
            CREATE TABLE paper_certification_assessments (
                assessment_id TEXT, dossier_id TEXT, evaluated_at TEXT, state TEXT,
                payload_json TEXT, payload_hash TEXT);
            CREATE TABLE paper_staged_rollout_plans (plan_id TEXT, session_id TEXT);
            CREATE TABLE paper_rollout_gate_assessments (
                assessment_id TEXT, plan_id TEXT, evaluated_at TEXT, state TEXT,
                payload_json TEXT, payload_hash TEXT);
            CREATE TABLE paper_stage_authorization_requests (request_id TEXT, session_id TEXT);
            CREATE TABLE paper_stage_authorization_assessments (
                assessment_id TEXT, request_id TEXT, evaluated_at TEXT, state TEXT,
                payload_json TEXT, payload_hash TEXT);
            CREATE TABLE paper_sandbox_stage_leases (lease_id TEXT, session_id TEXT);
            CREATE TABLE paper_sandbox_lease_assessments (
                assessment_id TEXT, lease_id TEXT, evaluated_at TEXT, state TEXT,
                payload_json TEXT, payload_hash TEXT);
        """)
        common = ("2026-09-10T14:00:00Z", payload_json, payload_hash)
        connection.execute(
            "INSERT INTO paper_burn_in_assessments VALUES (?,?,?,?,?,?)",
            ("burn-1", "paper-local-001", common[0], states["burn"], *common[1:]),
        )
        connection.execute("INSERT INTO paper_certification_dossiers VALUES (?,?)", (
            "dossier-1", "paper-local-001"
        ))
        connection.execute(
            "INSERT INTO paper_certification_assessments VALUES (?,?,?,?,?,?)",
            ("cert-1", "dossier-1", common[0], states["cert"], *common[1:]),
        )
        connection.execute("INSERT INTO paper_staged_rollout_plans VALUES (?,?)", (
            "plan-1", "paper-local-001"
        ))
        connection.execute(
            "INSERT INTO paper_rollout_gate_assessments VALUES (?,?,?,?,?,?)",
            ("rollout-1", "plan-1", common[0], states["rollout"], *common[1:]),
        )
        connection.execute("INSERT INTO paper_stage_authorization_requests VALUES (?,?)", (
            "request-1", "paper-local-001"
        ))
        connection.execute(
            "INSERT INTO paper_stage_authorization_assessments VALUES (?,?,?,?,?,?)",
            ("review-1", "request-1", common[0], states["review"], *common[1:]),
        )
        connection.execute("INSERT INTO paper_sandbox_stage_leases VALUES (?,?)", (
            "lease-1", "paper-local-001"
        ))
        connection.execute(
            "INSERT INTO paper_sandbox_lease_assessments VALUES (?,?,?,?,?,?)",
            ("lease-check-1", "lease-1", common[0], states["lease"], *common[1:]),
        )


def test_missing_evidence_is_deterministic_and_never_authorizes_launch(tmp_path: Path) -> None:
    _copy_status_config(tmp_path)
    config = load_launch_readiness_config(CONFIG)
    first = assess_local_launch_readiness(config, _operations(None), project_root=tmp_path)
    assert first == assess_local_launch_readiness(
        config, _operations(None), project_root=tmp_path
    )
    assert len(first.blocker_codes) == 5
    assert all(item.evidence_status == "MISSING" for item in first.evidence)
    assert not first.evidence_complete
    assert not first.launch_authorized
    assert not first.broker_write_performed


def test_complete_evidence_matrix_still_has_no_launch_authority(tmp_path: Path) -> None:
    _copy_status_config(tmp_path)
    database = tmp_path / "webull-sandbox.sqlite"
    _evidence_database(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    result = assess_local_launch_readiness(
        load_launch_readiness_config(CONFIG), _operations(), project_root=tmp_path
    )
    assert result.evidence_complete
    assert not result.blocker_codes
    assert all(item.evidence_status == "SATISFIED" for item in result.evidence)
    assert not result.launch_authorized
    assert not result.sandbox_execution_enabled
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_nonmatching_state_is_an_explicit_blocker(tmp_path: Path) -> None:
    _copy_status_config(tmp_path)
    _evidence_database(tmp_path / "webull-sandbox.sqlite", complete=False)
    result = assess_local_launch_readiness(
        load_launch_readiness_config(CONFIG), _operations(), project_root=tmp_path
    )
    assert "CERTIFICATION_UNSATISFIED" in result.blocker_codes
    certification = next(item for item in result.evidence if item.category == "certification")
    assert certification.observed_state == "INCOMPLETE"


def test_tampered_evidence_is_rejected(tmp_path: Path) -> None:
    _copy_status_config(tmp_path)
    _evidence_database(tmp_path / "webull-sandbox.sqlite", tampered=True)
    with pytest.raises(ValueError, match="payload hash mismatch"):
        assess_local_launch_readiness(
            load_launch_readiness_config(CONFIG), _operations(), project_root=tmp_path
        )


def test_config_rejects_requirement_changes_and_authority(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["requirements"]["burn_in"] = "SKIP"
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LaunchReadinessConfigError, match="requirements"):
        load_launch_readiness_config(unsafe)
    raw["requirements"]["burn_in"] = "PASS"
    raw["authority"]["launch_authorization_enabled"] = True
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LaunchReadinessConfigError, match="authority"):
        load_launch_readiness_config(unsafe)


def test_desktop_cli_renders_incomplete_matrix_without_authority(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for source in (
        "config/desktop.phase9g.v1.yaml",
        "config/desktop.phase9h.v1.yaml",
        "config/desktop.phase9i.v1.yaml",
        "config/thresholds.phase1e.v1.yaml",
        "config/paper.phase3b.v1.yaml",
        "config/webull.sandbox.v1.yaml",
    ):
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / source).read_bytes())
    python = tmp_path / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("fixture", encoding="utf-8")
    database = tmp_path / "webull-sandbox.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(PaperSession(
            "paper-ui-001",
            datetime(2026, 9, 10, 14, 0, tzinfo=UTC),
            PaperMode.SHADOW,
            "test-code",
            "sha256:test-config",
            "fixture-data",
            "XNYS-test",
        ))
    assert main([
        "desktop", "render-readiness", "--config", str(CONFIG),
        "--project-root", str(tmp_path),
    ]) == 0
    artifact = json.loads(capsys.readouterr().out)
    document = Path(artifact["output_path"]).read_text(encoding="utf-8")
    assert "Launch evidence" in document
    assert "INCOMPLETE" in document
    assert "Launch authorization</span><strong>DISABLED" in document
    assert "<script" not in document
