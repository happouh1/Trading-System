from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_replication_boundary_registry import (
    RangeReplicationBoundaryRegistry,
)
from trading_system.research.range_replication_collection import (
    load_range_replication_collection_config,
)
from trading_system.research.range_replication_collection_registry import (
    RangeReplicationCollectionRegistry,
)
from trading_system.research.range_replication_data_boundary import (
    InstrumentStatus,
    PointInTimeMembership,
    build_provider_manifest,
    build_universe_snapshot,
    load_range_replication_data_config,
)
from trading_system.research.range_replication_protocol_registry import (
    RangeReplicationProtocolStatus,
)
from trading_system.research.range_replication_security import (
    ReplicationRoleCredential,
    ReplicationSecurityRole,
    SignedReplicationAttestation,
    build_role_credential,
    load_range_replication_security_config,
    seal_outcome,
)
from trading_system.serialization import canonical_json, deterministic_id

ROOT = Path(__file__).parents[2]


def _protocol() -> RangeReplicationProtocolStatus:
    return RangeReplicationProtocolStatus(
        "protocol-8ij",
        "export-8ij",
        "report-8ij",
        "TEST_ONLY_8IJ",
        "2026-09-01T12:00:00.000000Z",
        "sha256:protocol-definition",
        True,
    )


def _credential(
    role: ReplicationSecurityRole,
    principal: str,
    valid_from: datetime,
    valid_until: datetime,
) -> ReplicationRoleCredential:
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return build_role_credential(
        principal_id=principal,
        role=role,
        public_key=public_key,
        valid_from=valid_from,
        valid_until=valid_until,
        issuer_id="TEST_ISSUER",
    )


def test_combined_data_security_boundary_is_causal_restart_safe_and_fail_closed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "phase8ij.sqlite"
    registered = datetime(2026, 9, 7, 12, tzinfo=UTC)
    start = registered + timedelta(days=2)
    end = start + timedelta(days=5)
    outcome_at = end + timedelta(days=1)
    collection_config = load_range_replication_collection_config(
        ROOT / "config/range_reclaim.phase8h.v1.yaml"
    )
    data_config = load_range_replication_data_config(
        ROOT / "config/range_reclaim.phase8i.v1.yaml"
    )
    security_config = load_range_replication_security_config(
        ROOT / "config/range_reclaim.phase8j.v1.yaml"
    )
    provider = build_provider_manifest(
        provider_id="TEST_PROVIDER",
        dataset_revision="revision-1",
        corporate_action_revision="actions-1",
        calendar_version="XNYS-2026",
        adjustment_policy="raw_and_split_adjusted",
        coverage_start=registered - timedelta(days=365),
        coverage_end=registered - timedelta(days=2),
        known_at=registered - timedelta(days=1),
        content_hash="sha256:test-provider-content",
        manifest_signature_id="test-signature-reference",
    )
    membership = PointInTimeMembership(
        "instrument-aapl",
        "AAPL",
        "XNAS",
        registered - timedelta(days=365),
        None,
        InstrumentStatus.ACTIVE,
        "sha256:test-membership",
    )
    universe = build_universe_snapshot(
        universe_name="TEST_POINT_IN_TIME_UNIVERSE",
        provider_manifest_id=provider.manifest_id,
        as_of=registered - timedelta(hours=2),
        known_at=registered - timedelta(hours=1),
        memberships=(membership,),
    )
    with SQLiteRepository(database) as repository:
        repository.migrate()
        collections = RangeReplicationCollectionRegistry(repository)
        collection = collections.create(
            collection_config,
            protocol=_protocol(),
            dataset_id="TEST_ONLY_8IJ",
            registered_at=registered,
            collection_start=start,
            collection_end=end,
        )
        boundary = RangeReplicationBoundaryRegistry(repository)
        boundary.register_provider_manifest(provider)
        boundary.register_universe_snapshot(universe)
        binding = boundary.bind_collection_data(
            data_config,
            collection_id=collection.collection_id,
            provider_manifest=provider,
            universe_snapshot=universe,
            bound_at=registered + timedelta(hours=1),
        )
        assert not binding.real_data_ready
        with pytest.raises(ValueError, match="before collection starts"):
            boundary.bind_collection_data(
                data_config,
                collection_id=collection.collection_id,
                provider_manifest=provider,
                universe_snapshot=universe,
                bound_at=start,
            )
        credentials = (
            _credential(
                ReplicationSecurityRole.COLLECTOR,
                "collector-1",
                registered,
                outcome_at + timedelta(days=2),
            ),
            _credential(
                ReplicationSecurityRole.OUTCOME_STEWARD,
                "steward-1",
                registered,
                outcome_at + timedelta(days=2),
            ),
            _credential(
                ReplicationSecurityRole.ANALYSIS_REVIEWER,
                "reviewer-1",
                registered,
                outcome_at + timedelta(days=2),
            ),
        )
        for credential in credentials:
            boundary.register_role_credential(credential)
        auditor_private = Ed25519PrivateKey.generate()
        auditor_public = auditor_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        auditor = build_role_credential(
            principal_id="auditor-1",
            role=ReplicationSecurityRole.SECURITY_AUDITOR,
            public_key=auditor_public,
            valid_from=registered,
            valid_until=outcome_at + timedelta(days=2),
            issuer_id="TEST_ISSUER",
        )
        boundary.register_role_credential(auditor)
        signed_at = registered + timedelta(minutes=1)
        signed_payload = {
            "principal_id": auditor.principal_id,
            "role": auditor.role.value,
            "security_boundary_version": "8J.1.0",
            "signed_at": signed_at,
            "subject_hash": provider.content_hash,
            "trusted_timestamp_token": "TEST_EXTERNAL_TIMESTAMP",
        }
        signature = auditor_private.sign(canonical_json(signed_payload).encode("utf-8"))
        signature_b64 = base64.b64encode(signature).decode("ascii")
        attestation = SignedReplicationAttestation(
            deterministic_id(
                "replication_attestation",
                {**signed_payload, "signature": signature_b64},
            ),
            provider.content_hash,
            auditor.principal_id,
            auditor.role,
            signed_at,
            "TEST_EXTERNAL_TIMESTAMP",
            signature_b64,
        )
        boundary.register_attestation(
            attestation,
            credential=auditor,
            timestamp_verifier=lambda token, subject, when: (
                token == "TEST_EXTERNAL_TIMESTAMP"
                and subject == provider.content_hash
                and when == signed_at
            ),
        )
        boundary.append_access_event(
            principal_id="collector-1",
            role=ReplicationSecurityRole.COLLECTOR,
            action="START_COLLECTION",
            subject_id=collection.collection_id,
            occurred_at=start,
            allowed=True,
        )
        collections.start(collection.collection_id, start)
        prediction = collections.append_prediction(
            collection.collection_id,
            hypothesis_id="hypothesis-1",
            box_id="box-1",
            symbol="AAPL",
            known_at=start + timedelta(hours=1),
            earliest_outcome_at=outcome_at,
            evidence_hash="sha256:prediction-evidence",
        )
        collections.close(collection.collection_id, end)
        envelope = seal_outcome(
            collection_id=collection.collection_id,
            prediction_id=prediction.prediction_id,
            key_id="TEST_KEY_1",
            key=bytes(range(32)),
            outcome_payload={"net_directional_return": "0.25"},
            sealed_at=outcome_at,
            nonce=b"0123456789ab",
            test_nonce_authorized=True,
        )
        with pytest.raises(PermissionError, match="outcome steward"):
            boundary.store_sealed_outcome(envelope, steward=credentials[0])
        boundary.store_sealed_outcome(envelope, steward=credentials[1])
        status = boundary.status(collection.collection_id, security_config)
        assert status.data_binding_present
        assert status.provider_attested
        assert status.required_roles_separated
        assert status.sealed_outcome_count == 1
        assert status.access_chain_valid
        assert not status.survivorship_safe_universe_claimed
        assert not status.external_trust_service_configured
        assert not status.real_collection_ready
        assert not status.real_blinding_attested
        assert not status.production_authority

    with SQLiteRepository(database) as repository:
        repository.migrate()
        boundary = RangeReplicationBoundaryRegistry(repository)
        restarted = boundary.status(collection.collection_id, security_config)
        assert restarted == status
        repository.connection.execute(
            "UPDATE replication_access_events SET prior_event_hash = 'sha256:tampered'"
        )
        repository.connection.commit()
        assert not boundary.status(collection.collection_id, security_config).access_chain_valid
