from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6t import CONFIG as REVIEW_CONFIG
from tests.unit.test_phase6t import service as review_service
from tests.unit.test_phase6t import signing_request
from trading_system.operations import (
    ArtifactTrustPolicyProposal,
    ArtifactTrustPolicyProposalConfigError,
    ArtifactTrustPolicyProposalRegistry,
    ArtifactTrustPolicyProposalStatus,
    ArtifactTrustReviewExportRegistry,
    ArtifactTrustReviewVerificationStatus,
    load_artifact_trust_policy_proposal_config,
    load_artifact_trust_review_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6u.v1.yaml"
ANSWERS = {
    "signature_algorithm": "candidate-algorithm-reference",
    "key_custody": "candidate-custody-reference",
    "signer_identity": "candidate-identity-reference",
    "trusted_timestamp_provider": "candidate-timestamp-reference",
    "revocation_policy": "candidate-revocation-reference",
    "receiving_verifier": "candidate-verifier-reference",
}


def verified_review(repository: SQLiteRepository) -> tuple[str, str]:
    service = review_service(repository)
    manifest = service.export(
        signing_request_id=signing_request(repository),
        exported_at=AS_OF + timedelta(hours=25),
        source_revision="sha256:phase6u-review-export",
    )
    verification = service.verify(
        export_id=manifest.export_id,
        verified_at=AS_OF + timedelta(hours=26),
        source_revision="sha256:phase6u-review-verification",
    )
    assert verification.status is ArtifactTrustReviewVerificationStatus.VERIFIED
    return manifest.export_id, verification.verification_id


def registry(repository: SQLiteRepository) -> ArtifactTrustPolicyProposalRegistry:
    review_config = load_artifact_trust_review_export_config(REVIEW_CONFIG)
    return ArtifactTrustPolicyProposalRegistry(
        repository,
        load_artifact_trust_policy_proposal_config(CONFIG),
        ArtifactTrustReviewExportRegistry(repository, review_config),
    )


def create_proposal(
    store: ArtifactTrustPolicyProposalRegistry,
    export_id: str,
    verification_id: str,
    *,
    proposed_at: datetime = AS_OF + timedelta(hours=27),
    answers: dict[str, str] | None = None,
) -> ArtifactTrustPolicyProposal:
    values = ANSWERS if answers is None else answers
    return store.create(
        review_export_id=export_id,
        review_verification_id=verification_id,
        proposed_at=proposed_at,
        source_revision="sha256:phase6u-proposal",
        **values,
    )


def test_config_rejects_authority_controls_and_thresholds(tmp_path: Path) -> None:
    assert load_artifact_trust_policy_proposal_config(CONFIG).config_hash.startswith("sha256:")
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["policy_activation_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustPolicyProposalConfigError, match="no approval"):
        load_artifact_trust_policy_proposal_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["proposal"]["status"] = "APPROVED"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustPolicyProposalConfigError, match="mandatory"):
        load_artifact_trust_policy_proposal_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["approval_threshold_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustPolicyProposalConfigError, match="cannot invent"):
        load_artifact_trust_policy_proposal_config(invalid)


def test_proposal_is_deterministic_unauthenticated_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        store = registry(repository)
        proposal = create_proposal(store, export_id, verification_id)
        assert store.insert(proposal)
        assert not store.insert(proposal)
        assert proposal.status is ArtifactTrustPolicyProposalStatus.PROPOSED_UNAUTHENTICATED
        assert "UNRESOLVED" not in proposal.answers
    with SQLiteRepository(database) as repository:
        repository.migrate()
        assert registry(repository).proposal(proposal.proposal_id) == proposal


def test_proposal_rejects_noncausal_unresolved_and_secret_material(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        store = registry(repository)
        with pytest.raises(ValueError, match="predate"):
            create_proposal(
                store,
                export_id,
                verification_id,
                proposed_at=AS_OF + timedelta(hours=25),
            )
        unresolved = dict(ANSWERS)
        unresolved["signature_algorithm"] = "UNRESOLVED"
        with pytest.raises(ValueError, match="answer is invalid"):
            create_proposal(store, export_id, verification_id, answers=unresolved)
        secret = dict(ANSWERS)
        secret["key_custody"] = "-----BEGIN PRIVATE KEY-----"
        with pytest.raises(ValueError, match="secret or key"):
            create_proposal(store, export_id, verification_id, answers=secret)


def test_proposal_rejects_corrupt_phase6t_verification(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_review(repository)
        repository.connection.execute(
            """UPDATE operations_artifact_trust_review_export_verifications
            SET payload_hash='sha256:corrupt' WHERE verification_id=?""",
            (verification_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            create_proposal(registry(repository), export_id, verification_id)


def test_phase6u_migration_copies_match() -> None:
    root = ROOT / "migrations" / "048_phase_6u_artifact_trust_policy_proposals.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
