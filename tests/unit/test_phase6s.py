from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.unit.test_phase6a import AS_OF
from tests.unit.test_phase6r import CONFIG as EXPORT_CONFIG
from tests.unit.test_phase6r import export_service, seed_materialization
from trading_system.cli import main
from trading_system.operations import (
    ArtifactSigningRequestStatus,
    ArtifactTrustConfigError,
    ArtifactTrustPolicyStatus,
    ArtifactTrustRegistry,
    load_artifact_trust_config,
    load_prospective_review_bundle_chain_export_config,
)
from trading_system.persistence import SQLiteRepository

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "config" / "operations.phase6s.v1.yaml"


def verified_export(repository: SQLiteRepository) -> tuple[str, str]:
    service = export_service(repository)
    manifest = service.export(
        materialization_id=seed_materialization(repository),
        exported_at=AS_OF + timedelta(hours=21),
        source_revision="sha256:phase6s-export",
    )
    verification = service.verify(
        export_id=manifest.export_id,
        verified_at=AS_OF + timedelta(hours=22),
        source_revision="sha256:phase6s-verification",
    )
    return manifest.export_id, verification.verification_id


def registry(repository: SQLiteRepository) -> ArtifactTrustRegistry:
    return ArtifactTrustRegistry(
        repository,
        load_artifact_trust_config(CONFIG),
        load_prospective_review_bundle_chain_export_config(EXPORT_CONFIG),
    )


def test_config_rejects_authority_resolved_policy_and_threshold(tmp_path: Path) -> None:
    config = load_artifact_trust_config(CONFIG)
    assert config.signature_algorithm == "UNRESOLVED"
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    invalid = tmp_path / "invalid.json"
    raw["authority"]["signing_enabled"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustConfigError, match="no signing"):
        load_artifact_trust_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["policy"]["signature_algorithm"] = "invented"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustConfigError, match="unresolved"):
        load_artifact_trust_config(invalid)
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["thresholds"]["minimum_signer_count_defined"] = True
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ArtifactTrustConfigError, match="cannot invent"):
        load_artifact_trust_config(invalid)


def test_policy_and_request_are_deterministic_blocked_and_restart_safe(tmp_path: Path) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = verified_export(repository)
        store = registry(repository)
        policy = store.create_policy(
            registered_at=AS_OF + timedelta(hours=23),
            source_revision="sha256:phase6s-policy",
        )
        assert store.insert_policy(policy)
        assert not store.insert_policy(policy)
        request = store.request_signing(
            policy_id=policy.policy_id,
            export_id=export_id,
            export_verification_id=verification_id,
            requested_at=AS_OF + timedelta(hours=24),
            source_revision="sha256:phase6s-request",
        )
        assert store.insert_request(request)
        assert not store.insert_request(request)
        assert policy.status is ArtifactTrustPolicyStatus.BLOCKED_UNCONFIGURED
        assert request.status is ArtifactSigningRequestStatus.BLOCKED_UNCONFIGURED
        assert request.signed is request.trusted_timestamped is False
        assert len(request.blockers) == 6
    with SQLiteRepository(database) as repository:
        repository.migrate()
        store = registry(repository)
        assert store.policy(policy.policy_id) == policy
        assert store.request(request.request_id) == request


def test_request_rejects_noncausal_or_duplicate_evidence(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_export(repository)
        store = registry(repository)
        policy = store.create_policy(
            registered_at=AS_OF + timedelta(hours=23),
            source_revision="sha256:policy",
        )
        assert store.insert_policy(policy)
        with pytest.raises(ValueError, match="predate"):
            store.request_signing(
                policy_id=policy.policy_id,
                export_id=export_id,
                export_verification_id=verification_id,
                requested_at=AS_OF + timedelta(hours=22),
                source_revision="sha256:early",
            )
        request = store.request_signing(
            policy_id=policy.policy_id,
            export_id=export_id,
            export_verification_id=verification_id,
            requested_at=AS_OF + timedelta(hours=24),
            source_revision="sha256:first",
        )
        assert store.insert_request(request)
        duplicate = store.request_signing(
            policy_id=policy.policy_id,
            export_id=export_id,
            export_verification_id=verification_id,
            requested_at=AS_OF + timedelta(hours=25),
            source_revision="sha256:second",
        )
        with pytest.raises(ValueError, match="already has"):
            store.insert_request(duplicate)


def test_request_rejects_corrupt_phase6r_verification(tmp_path: Path) -> None:
    with SQLiteRepository(tmp_path / "operations.sqlite") as repository:
        repository.migrate()
        export_id, verification_id = verified_export(repository)
        store = registry(repository)
        policy = store.create_policy(
            registered_at=AS_OF + timedelta(hours=23),
            source_revision="sha256:policy",
        )
        assert store.insert_policy(policy)
        repository.connection.execute(
            """UPDATE operations_prospective_review_bundle_chain_export_verifications
            SET payload_hash='sha256:corrupt' WHERE verification_id=?""",
            (verification_id,),
        )
        repository.connection.commit()
        with pytest.raises(ValueError, match="corrupt"):
            store.request_signing(
                policy_id=policy.policy_id,
                export_id=export_id,
                export_verification_id=verification_id,
                requested_at=AS_OF + timedelta(hours=24),
                source_revision="sha256:request",
            )


def test_phase6s_cli_is_explicitly_unsigned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "operations.sqlite"
    with SQLiteRepository(database) as repository:
        repository.migrate()
        export_id, verification_id = verified_export(repository)
    policy_input = tmp_path / "policy.json"
    policy_input.write_text(
        json.dumps(
            {
                "registered_at": (AS_OF + timedelta(hours=23)).isoformat(),
                "source_revision": "sha256:cli-policy",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "register-artifact-trust-policy",
            "--config",
            str(CONFIG),
            "--export-config",
            str(EXPORT_CONFIG),
            "--input",
            str(policy_input),
            "--database",
            str(database),
        ]
    ) == 0
    policy_output = json.loads(capsys.readouterr().out)
    policy_id = policy_output["evidence"]["policy"]["policy_id"]
    request_input = tmp_path / "request.json"
    request_input.write_text(
        json.dumps(
            {
                "policy_id": policy_id,
                "export_id": export_id,
                "export_verification_id": verification_id,
                "requested_at": (AS_OF + timedelta(hours=24)).isoformat(),
                "source_revision": "sha256:cli-request",
            }
        ),
        encoding="utf-8",
    )
    assert main(
        [
            "operations",
            "request-artifact-signing",
            "--config",
            str(CONFIG),
            "--export-config",
            str(EXPORT_CONFIG),
            "--input",
            str(request_input),
            "--database",
            str(database),
        ]
    ) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["evidence"]["request"]["status"] == "BLOCKED_UNCONFIGURED"
    for key in (
        "signed",
        "trusted_timestamped",
        "key_material_used",
        "credentials_used",
        "external_transport_used",
        "production_readiness_claim",
        "automatic_promotion_performed",
        "network_used",
        "broker_write_performed",
        "live_trading_enabled",
    ):
        assert output[key] is False


def test_phase6s_migration_copies_match() -> None:
    root = ROOT / "migrations" / "046_phase_6s_artifact_trust_foundation.sql"
    packaged = ROOT / "src" / "trading_system" / "persistence" / "migrations" / root.name
    assert root.read_bytes() == packaged.read_bytes()
