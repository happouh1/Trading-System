from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.paper.burn_in import BurnInState, PaperBurnInAssessment
from trading_system.paper.certification import (
    CertificationAssessment,
    CertificationEvidence,
    CertificationState,
    build_certification_dossier,
    load_paper_certification_config,
)
from trading_system.paper.certification_registry import PaperCertificationRegistry
from trading_system.paper.rollout import (
    build_rollout_stage,
    build_rollout_stage_evidence,
    build_staged_rollout_plan,
    evaluate_rollout_stage,
    load_paper_rollout_config,
)
from trading_system.paper.rollout_registry import PaperRolloutRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]


def test_phase9d_registry_is_restart_safe_and_tamper_evident(tmp_path: Path) -> None:
    database = tmp_path / "phase9d.sqlite"
    now = datetime(2026, 9, 9, 12, tzinfo=UTC)
    burn = PaperBurnInAssessment(
        "assessment-9b", "protocol-9b", "paper-9d", now - timedelta(days=1),
        BurnInState.PASS, 100, 0, Decimal(0), 0, 0, "sha256:snapshots", (),
        "sha256:burn-protocol", "sha256:burn-config",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(PaperSession(
            "paper-9d", now - timedelta(days=3), PaperMode.SHADOW, "code",
            "sha256:paper-config", "revision", "calendar",
        ))
        repository.connection.execute(
            """INSERT INTO paper_burn_in_protocols
               (protocol_id, session_id, declared_at, window_start, window_end,
                definition_hash, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("protocol-9b", "paper-9d", "2026-09-01T00:00:00.000000Z",
             "2026-09-02T00:00:00.000000Z", "2026-09-08T00:00:00.000000Z",
             "sha256:burn-protocol", "sha256:burn-config", "{}", canonical_hash({})),
        )
        repository.connection.execute(
            """INSERT INTO paper_burn_in_assessments
               (assessment_id, protocol_id, session_id, evaluated_at, state,
                snapshot_root_hash, payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (burn.assessment_id, burn.protocol_id, burn.session_id,
             "2026-09-08T12:00:00.000000Z", burn.state.value, burn.snapshot_root_hash,
             canonical_json(burn), canonical_hash(burn)),
        )
        repository.connection.commit()
        certification_config = load_paper_certification_config(
            ROOT / "config/paper.phase9c.v1.yaml"
        )
        dossier = build_certification_dossier(
            certification_config, burn_in=burn, declared_at=now,
            required_evidence_types=("OPERATIONS",),
            required_review_roles=("OPERATIONS_REVIEWER",),
            evidence=(CertificationEvidence("OPERATIONS", "sha256:operations", now),),
        )
        certification_registry = PaperCertificationRegistry(repository)
        assert certification_registry.register_dossier(dossier)
        certification = CertificationAssessment(
            "assessment-9c", dossier.dossier_id, now, CertificationState.REVIEW_READY,
            ("OPERATIONS_REVIEWER",), (), dossier.dossier_hash, dossier.config_hash,
        )
        assert certification_registry.record_assessment(certification)

        rollout_config = load_paper_rollout_config(ROOT / "config/paper.phase9d.v1.yaml")
        stage = build_rollout_stage(
            stage_id="OBSERVE", sequence=1, capital_ceiling=Decimal("1000"),
            position_ceiling=1, minimum_observations=5,
            rollback_trigger_codes=("HALT",),
        )
        plan = build_staged_rollout_plan(
            rollout_config, certification=certification, session_id="paper-9d",
            declared_at=now + timedelta(hours=1), stages=(stage,),
        )
        registry = PaperRolloutRegistry(repository)
        assert registry.register_plan(plan)
        assert not registry.register_plan(plan)
        evidence = build_rollout_stage_evidence(
            plan, stage_id="OBSERVE", observed_at=now + timedelta(hours=2),
            completed_observations=5, unresolved_incidents=0,
            breached_trigger_codes=(), source_hash="sha256:source",
        )
        assert registry.record_evidence(evidence)
        assessment = evaluate_rollout_stage(
            plan, evidence, evaluated_at=now + timedelta(hours=3)
        )
        assert registry.record_assessment(assessment, evidence.evidence_id)
        assert not registry.record_assessment(assessment, evidence.evidence_id)

    with SQLiteRepository(database) as restarted:
        restarted.migrate()
        registry = PaperRolloutRegistry(restarted)
        assert not registry.record_assessment(assessment, evidence.evidence_id)
        restarted.connection.execute(
            "UPDATE paper_rollout_stage_evidence SET payload_json = '{}' WHERE evidence_id = ?",
            (evidence.evidence_id,),
        )
        restarted.connection.commit()
        with pytest.raises(ValueError, match="evidence dependency"):
            registry.record_assessment(assessment, evidence.evidence_id)


def test_phase9d_migration_copies_match() -> None:
    root = ROOT / "migrations/084_phase_9d_staged_rollout.sql"
    packaged = ROOT / "src/trading_system/persistence/migrations/084_phase_9d_staged_rollout.sql"
    assert root.read_bytes() == packaged.read_bytes()
