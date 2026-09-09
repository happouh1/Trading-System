from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.paper.burn_in import BurnInState, PaperBurnInAssessment
from trading_system.paper.certification import (
    CertificationDossier,
    CertificationEvidence,
    CertificationState,
    PaperCertificationConfigError,
    attestation_message,
    build_certification_attestation,
    build_certification_credential,
    build_certification_dossier,
    evaluate_certification,
    load_paper_certification_config,
)

ROOT = Path(__file__).parents[2]


def _burn_in() -> PaperBurnInAssessment:
    return PaperBurnInAssessment(
        "assessment-9b", "protocol-9b", "paper-9c",
        datetime(2026, 9, 8, 20, tzinfo=UTC), BurnInState.PASS, 100, 0,
        Decimal(0), 0, 0, "sha256:snapshots", (), "sha256:protocol",
        "sha256:burn-config",
    )


def _dossier() -> CertificationDossier:
    config = load_paper_certification_config(ROOT / "config/paper.phase9c.v1.yaml")
    declared = datetime(2026, 9, 9, 12, tzinfo=UTC)
    evidence = (
        CertificationEvidence("OPERATIONS", "sha256:operations", declared),
        CertificationEvidence("SECURITY", "sha256:security", declared),
    )
    return build_certification_dossier(
        config, burn_in=_burn_in(), declared_at=declared,
        required_evidence_types=("SECURITY", "OPERATIONS"),
        required_review_roles=("SECURITY_REVIEWER", "OPERATIONS_REVIEWER"),
        evidence=tuple(reversed(evidence)),
    )


def test_signed_dossier_becomes_review_ready_without_certifying() -> None:
    dossier = _dossier()
    credentials = []
    attestations = []
    for role in dossier.required_review_roles:
        private = Ed25519PrivateKey.generate()
        credential = build_certification_credential(
            principal_id=f"principal-{role}", role=role,
            public_key=private.public_key().public_bytes_raw(),
            valid_from=dossier.declared_at - timedelta(days=1),
            valid_until=dossier.declared_at + timedelta(days=2),
        )
        signed_at = dossier.declared_at + timedelta(hours=1)
        signature = private.sign(attestation_message(dossier, credential, signed_at))
        credentials.append(credential)
        attestations.append(build_certification_attestation(
            dossier, credential, signed_at=signed_at, signature=signature
        ))
    assessment = evaluate_certification(
        dossier, credentials=tuple(credentials), attestations=tuple(reversed(attestations)),
        evaluated_at=dossier.declared_at + timedelta(hours=2),
    )
    assert assessment.state is CertificationState.REVIEW_READY
    assert not assessment.certified
    assert not assessment.deployment_authorized


def test_missing_signature_is_incomplete_and_bad_signature_is_blocked() -> None:
    dossier = _dossier()
    private = Ed25519PrivateKey.generate()
    credential = build_certification_credential(
        principal_id="operator", role="OPERATIONS_REVIEWER",
        public_key=private.public_key().public_bytes_raw(),
        valid_from=dossier.declared_at, valid_until=dossier.declared_at + timedelta(days=1),
    )
    signed_at = dossier.declared_at + timedelta(hours=1)
    valid = build_certification_attestation(
        dossier, credential, signed_at=signed_at,
        signature=private.sign(attestation_message(dossier, credential, signed_at)),
    )
    incomplete = evaluate_certification(
        dossier, credentials=(credential,), attestations=(valid,),
        evaluated_at=signed_at,
    )
    assert incomplete.state is CertificationState.INCOMPLETE
    bad = build_certification_attestation(
        dossier, credential, signed_at=signed_at, signature=b"invalid-signature"
    )
    blocked = evaluate_certification(
        dossier, credentials=(credential,), attestations=(bad,), evaluated_at=signed_at
    )
    assert blocked.state is CertificationState.BLOCKED


def test_dossier_rejects_nonpassing_burn_in_and_missing_evidence() -> None:
    config = load_paper_certification_config(ROOT / "config/paper.phase9c.v1.yaml")
    failed = PaperBurnInAssessment(
        "failed", "protocol", "paper-9c", datetime(2026, 9, 8, tzinfo=UTC),
        BurnInState.FAIL, 1, 1, Decimal(1), 1, 0, "sha256:snapshots",
        ("FAIL",), "sha256:protocol", "sha256:config",
    )
    with pytest.raises(ValueError, match="passing"):
        build_certification_dossier(
            config, burn_in=failed, declared_at=datetime(2026, 9, 9, tzinfo=UTC),
            required_evidence_types=("SECURITY",), required_review_roles=("REVIEWER",),
            evidence=(),
        )


def test_config_rejects_certification_authority(tmp_path: Path) -> None:
    source = ROOT / "config/paper.phase9c.v1.yaml"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["authority"]["certification_grant_enabled"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PaperCertificationConfigError, match="authority"):
        load_paper_certification_config(unsafe)
