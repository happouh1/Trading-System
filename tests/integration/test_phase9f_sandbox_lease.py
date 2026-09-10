from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.paper.certification import CertificationAssessment, CertificationState
from trading_system.paper.rollout import (
    build_rollout_stage,
    build_staged_rollout_plan,
    load_paper_rollout_config,
)
from trading_system.paper.sandbox_lease import (
    build_sandbox_lease_revocation,
    build_sandbox_stage_lease,
    evaluate_sandbox_lease,
    load_sandbox_lease_config,
)
from trading_system.paper.sandbox_lease_registry import SandboxLeaseRegistry
from trading_system.paper.stage_authorization import (
    StageAuthorizationAssessment,
    StageAuthorizationState,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]


def test_phase9f_registry_is_restart_safe_and_tamper_evident(tmp_path: Path) -> None:
    database = tmp_path / "phase9f.sqlite"
    now = datetime(2026, 9, 10, 14, tzinfo=UTC)
    certification = CertificationAssessment(
        "certification", "dossier", now - timedelta(days=1),
        CertificationState.REVIEW_READY, ("REVIEWER",), (),
        "sha256:dossier", "sha256:certification-config",
    )
    stage = build_rollout_stage(
        stage_id="OBSERVE", sequence=1, capital_ceiling=Decimal("1000"),
        position_ceiling=1, minimum_observations=1, rollback_trigger_codes=("HALT",),
    )
    plan = build_staged_rollout_plan(
        load_paper_rollout_config(ROOT / "config/paper.phase9d.v1.yaml"),
        certification=certification, session_id="paper-9f",
        declared_at=now - timedelta(hours=2), stages=(stage,),
    )
    authorization = StageAuthorizationAssessment(
        "authorization", "request", plan.plan_id, stage.stage_id,
        now - timedelta(hours=1), StageAuthorizationState.SIGNATURES_VERIFIED,
        ("REVIEWER",), (), "sha256:request", "sha256:authorization-config",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(PaperSession(
            "paper-9f", now - timedelta(days=1), PaperMode.SHADOW, "code",
            "sha256:paper-config", "revision", "calendar",
        ))
        repository.connection.execute("PRAGMA foreign_keys = OFF")
        repository.connection.execute(
            """INSERT INTO paper_staged_rollout_plans
               (plan_id, session_id, certification_assessment_id, declared_at, plan_hash,
                config_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (plan.plan_id, plan.session_id, plan.certification_assessment_id,
             plan.declared_at.isoformat(), plan.plan_hash, plan.config_hash,
             canonical_json(plan), canonical_hash(plan)),
        )
        repository.connection.execute(
            """INSERT INTO paper_rollout_stages
               (plan_id, stage_id, sequence, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (plan.plan_id, stage.stage_id, stage.sequence,
             canonical_json(stage), canonical_hash(stage)),
        )
        repository.connection.execute(
            """INSERT INTO paper_stage_authorization_requests
               (request_id, session_id, rollout_assessment_id, plan_id, stage_id,
                requested_at, valid_from, valid_until, request_hash, config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("request", plan.session_id, "rollout-assessment", plan.plan_id, stage.stage_id,
             now.isoformat(), now.isoformat(), (now + timedelta(hours=2)).isoformat(),
             "sha256:request", "sha256:authorization-config", "{}", canonical_hash({})),
        )
        repository.connection.execute(
            """INSERT INTO paper_stage_authorization_assessments
               (assessment_id, request_id, plan_id, stage_id, evaluated_at, state,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (authorization.assessment_id, authorization.request_id, authorization.plan_id,
             authorization.stage_id, authorization.evaluated_at.isoformat(),
             authorization.state.value, canonical_json(authorization),
             canonical_hash(authorization)),
        )
        repository.connection.commit()
        repository.connection.execute("PRAGMA foreign_keys = ON")

        lease = build_sandbox_stage_lease(
            load_sandbox_lease_config(ROOT / "config/paper.phase9f.v1.yaml"),
            authorization=authorization, plan=plan, issued_at=now,
            valid_from=now, valid_until=now + timedelta(hours=1),
        )
        registry = SandboxLeaseRegistry(repository)
        assert registry.register_lease(lease)
        assert not registry.register_lease(lease)
        opened = evaluate_sandbox_lease(lease, evaluated_at=now + timedelta(minutes=1))
        assert registry.record_assessment(opened)
        revocation = build_sandbox_lease_revocation(
            lease, revoked_at=now + timedelta(minutes=2), reason_code="OPERATOR_HALT"
        )
        assert registry.record_revocation(revocation)
        revoked = evaluate_sandbox_lease(
            lease, evaluated_at=now + timedelta(minutes=2), revocation=revocation
        )
        assert registry.record_assessment(revoked, revocation_id=revocation.revocation_id)

    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        registry = SandboxLeaseRegistry(restarted)
        assert not registry.record_assessment(
            revoked, revocation_id=revocation.revocation_id
        )
        restarted.connection.execute(
            "UPDATE paper_sandbox_stage_leases SET payload_json = '{}' WHERE lease_id = ?",
            (lease.lease_id,),
        )
        restarted.connection.commit()
        with pytest.raises(ValueError, match="lease dependency"):
            registry.record_assessment(revoked, revocation_id=revocation.revocation_id)


def test_phase9f_migration_copies_match() -> None:
    root = ROOT / "migrations/086_phase_9f_sandbox_leases.sql"
    packaged = ROOT / "src/trading_system/persistence/migrations/086_phase_9f_sandbox_leases.sql"
    assert root.read_bytes() == packaged.read_bytes()
