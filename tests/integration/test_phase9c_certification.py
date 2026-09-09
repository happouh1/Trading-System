from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.paper import PaperMode, PaperRegistry, PaperSession
from trading_system.paper.burn_in import BurnInState, PaperBurnInAssessment
from trading_system.paper.certification import (
    CertificationEvidence,
    attestation_message,
    build_certification_attestation,
    build_certification_credential,
    build_certification_dossier,
    evaluate_certification,
    load_paper_certification_config,
)
from trading_system.paper.certification_registry import PaperCertificationRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json

ROOT = Path(__file__).parents[2]


def test_phase9c_registry_is_idempotent_and_tamper_evident(tmp_path: Path) -> None:
    database = tmp_path / "phase9c.sqlite"
    now = datetime(2026, 9, 9, 12, tzinfo=UTC)
    burn = PaperBurnInAssessment(
        "assessment-9b", "protocol-9b", "paper-9c", now - timedelta(days=1),
        BurnInState.PASS, 100, 0, Decimal(0), 0, 0, "sha256:snapshots", (),
        "sha256:burn-protocol", "sha256:burn-config",
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        PaperRegistry(repository).insert_session(PaperSession(
            "paper-9c", now - timedelta(days=3), PaperMode.SHADOW, "code",
            "sha256:paper-config", "revision", "calendar",
        ))
        repository.connection.execute(
            """INSERT INTO paper_burn_in_protocols
               (protocol_id, session_id, declared_at, window_start, window_end,
                definition_hash, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("protocol-9b", "paper-9c", "2026-09-01T00:00:00.000000Z",
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
        config = load_paper_certification_config(ROOT / "config/paper.phase9c.v1.yaml")
        dossier = build_certification_dossier(
            config, burn_in=burn, declared_at=now,
            required_evidence_types=("OPERATIONS",),
            required_review_roles=("OPERATIONS_REVIEWER",),
            evidence=(CertificationEvidence("OPERATIONS", "sha256:operations", now),),
        )
        registry = PaperCertificationRegistry(repository)
        assert registry.register_dossier(dossier)
        assert not registry.register_dossier(dossier)
        private = Ed25519PrivateKey.generate()
        credential = build_certification_credential(
            principal_id="operator", role="OPERATIONS_REVIEWER",
            public_key=private.public_key().public_bytes_raw(),
            valid_from=now, valid_until=now + timedelta(days=1),
        )
        signed_at = now + timedelta(hours=1)
        attestation = build_certification_attestation(
            dossier, credential, signed_at=signed_at,
            signature=private.sign(attestation_message(dossier, credential, signed_at)),
        )
        assert registry.record_attestation(attestation)
        assessment = evaluate_certification(
            dossier, credentials=(credential,), attestations=(attestation,),
            evaluated_at=signed_at,
        )
        assert registry.record_assessment(assessment)
        assert not registry.record_assessment(assessment)
        repository.connection.execute(
            "UPDATE paper_certification_dossiers SET payload_json = '{}' WHERE dossier_id = ?",
            (dossier.dossier_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="dossier dependency"):
            registry.record_assessment(assessment)
