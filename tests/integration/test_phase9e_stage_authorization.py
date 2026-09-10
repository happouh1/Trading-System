from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.paper.rollout import RolloutGateAssessment, RolloutGateState
from trading_system.paper.stage_authorization import (
    build_stage_authorization_request,
    build_stage_review_attestation,
    build_stage_review_credential,
    evaluate_stage_authorization,
    load_stage_authorization_config,
    stage_review_message,
)
from trading_system.paper.stage_authorization_registry import StageAuthorizationRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]


def test_phase9e_registry_is_restart_safe_and_tamper_evident(tmp_path: Path) -> None:
    database = tmp_path / "phase9e.sqlite"
    now = datetime(2026, 9, 9, 16, tzinfo=UTC)
    rollout = RolloutGateAssessment(
        "rollout-assessment", "rollout-plan", "OBSERVE", now,
        RolloutGateState.READY_FOR_HUMAN_REVIEW, (), "sha256:evidence",
        "sha256:plan", "sha256:rollout-config",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(PaperSession(
            "paper-9e", now - timedelta(days=1), PaperMode.SHADOW, "code",
            "sha256:paper-config", "revision", "calendar",
        ))
        repository.connection.execute("PRAGMA foreign_keys = OFF")
        repository.connection.execute(
            """INSERT INTO paper_staged_rollout_plans
               (plan_id, session_id, certification_assessment_id, declared_at, plan_hash,
                config_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("rollout-plan", "paper-9e", "certification-assessment",
             "2026-09-09T14:00:00.000000Z", "sha256:plan", "sha256:rollout-config",
             "{}", canonical_hash({})),
        )
        repository.connection.execute(
            """INSERT INTO paper_rollout_stages
               (plan_id, stage_id, sequence, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?)""",
            ("rollout-plan", "OBSERVE", 1, "{}", canonical_hash({})),
        )
        repository.connection.execute(
            """INSERT INTO paper_rollout_stage_evidence
               (evidence_id, plan_id, stage_id, observed_at, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("rollout-evidence", "rollout-plan", "OBSERVE",
             "2026-09-09T15:00:00.000000Z", "{}", canonical_hash({})),
        )
        repository.connection.execute(
            """INSERT INTO paper_rollout_gate_assessments
               (assessment_id, plan_id, stage_id, evidence_id, evaluated_at, state,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (rollout.assessment_id, rollout.plan_id, rollout.stage_id, "rollout-evidence",
             "2026-09-09T16:00:00.000000Z", rollout.state.value,
             canonical_json(rollout), canonical_hash(rollout)),
        )
        repository.connection.commit()
        repository.connection.execute("PRAGMA foreign_keys = ON")

        config = load_stage_authorization_config(ROOT / "config/paper.phase9e.v1.yaml")
        request = build_stage_authorization_request(
            config, rollout_assessment=rollout, session_id="paper-9e",
            requested_at=now, valid_from=now, valid_until=now + timedelta(hours=2),
            required_review_roles=("RISK_REVIEWER",),
        )
        registry = StageAuthorizationRegistry(repository)
        assert registry.register_request(request)
        assert not registry.register_request(request)
        private = Ed25519PrivateKey.generate()
        credential = build_stage_review_credential(
            principal_id="risk", role="RISK_REVIEWER",
            public_key=private.public_key().public_bytes_raw(),
            valid_from=now - timedelta(hours=1), valid_until=now + timedelta(days=1),
        )
        signed_at = now + timedelta(minutes=1)
        attestation = build_stage_review_attestation(
            request, credential, signed_at=signed_at,
            signature=private.sign(stage_review_message(request, credential, signed_at)),
        )
        assert registry.record_attestation(attestation)
        assessment = evaluate_stage_authorization(
            request, credentials=(credential,), attestations=(attestation,),
            evaluated_at=now + timedelta(minutes=2),
        )
        assert registry.record_assessment(assessment)
        assert not registry.record_assessment(assessment)

    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        registry = StageAuthorizationRegistry(restarted)
        assert not registry.record_assessment(assessment)
        restarted.connection.execute(
            """UPDATE paper_stage_authorization_requests SET payload_json = '{}'
               WHERE request_id = ?""",
            (request.request_id,),
        )
        restarted.connection.commit()
        with pytest.raises(ValueError, match="request dependency"):
            registry.record_assessment(assessment)


def test_phase9e_migration_copies_match() -> None:
    root = ROOT / "migrations/085_phase_9e_stage_authorization.sql"
    packaged = (
        ROOT
        / "src/trading_system/persistence/migrations/085_phase_9e_stage_authorization.sql"
    )
    assert root.read_bytes() == packaged.read_bytes()
