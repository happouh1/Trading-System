from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trading_system.research.range_replication_data_boundary import (
    InstrumentStatus,
    PointInTimeMembership,
    RangeReplicationDataConfigError,
    build_provider_manifest,
    build_universe_snapshot,
    load_range_replication_data_config,
)
from trading_system.research.range_replication_security import (
    RangeReplicationSecurityConfigError,
    ReplicationSecurityRole,
    SignedReplicationAttestation,
    build_access_event,
    build_role_credential,
    load_range_replication_security_config,
    open_outcome,
    seal_outcome,
    verify_attestation,
)
from trading_system.serialization import canonical_json, deterministic_id

ROOT = Path(__file__).parents[2]
DATA_CONFIG = ROOT / "config/range_reclaim.phase8i.v1.yaml"
SECURITY_CONFIG = ROOT / "config/range_reclaim.phase8j.v1.yaml"


def test_data_manifest_and_point_in_time_universe_are_deterministic() -> None:
    config = load_range_replication_data_config(DATA_CONFIG)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 9, 1, tzinfo=UTC)
    known = end + timedelta(days=1)
    provider = build_provider_manifest(
        provider_id="TEST_PROVIDER",
        dataset_revision="revision-1",
        corporate_action_revision="actions-1",
        calendar_version="XNYS-2026",
        adjustment_policy="raw_and_split_adjusted",
        coverage_start=start,
        coverage_end=end,
        known_at=known,
        content_hash="sha256:data",
    )
    first = PointInTimeMembership(
        "instrument-2",
        "MSFT",
        "XNYS",
        start,
        None,
        InstrumentStatus.ACTIVE,
        "sha256:member-2",
    )
    second = PointInTimeMembership(
        "instrument-1",
        "AAPL",
        "XNAS",
        start,
        None,
        InstrumentStatus.ACTIVE,
        "sha256:member-1",
    )
    snapshot_a = build_universe_snapshot(
        universe_name="TEST_UNIVERSE",
        provider_manifest_id=provider.manifest_id,
        as_of=end,
        known_at=known,
        memberships=(first, second),
    )
    snapshot_b = build_universe_snapshot(
        universe_name="TEST_UNIVERSE",
        provider_manifest_id=provider.manifest_id,
        as_of=end,
        known_at=known,
        memberships=(second, first),
    )
    assert config.config_hash.startswith("sha256:")
    assert snapshot_a == snapshot_b
    assert tuple(item.instrument_id for item in snapshot_a.memberships) == (
        "instrument-1",
        "instrument-2",
    )
    assert not provider.externally_attested
    assert not snapshot_a.survivorship_safe_claimed


def test_data_boundary_rejects_mutable_authority_and_inactive_membership(
    tmp_path: Path,
) -> None:
    raw = json.loads(DATA_CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["provider_selected"] = True
    path = tmp_path / "unsafe-data.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationDataConfigError, match="authority"):
        load_range_replication_data_config(path)
    with pytest.raises(ValueError, match="universe snapshot"):
        build_universe_snapshot(
            universe_name="TEST_UNIVERSE",
            provider_manifest_id="manifest",
            as_of=datetime(2026, 9, 1, tzinfo=UTC),
            known_at=datetime(2026, 9, 2, tzinfo=UTC),
            memberships=(
                PointInTimeMembership(
                    "instrument-1",
                    "AAPL",
                    "XNAS",
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 8, 1, tzinfo=UTC),
                    InstrumentStatus.DELISTED,
                    "sha256:member",
                ),
            ),
        )


def test_ed25519_attestation_and_aes_gcm_release_gates() -> None:
    config = load_range_replication_security_config(SECURITY_CONFIG)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    now = datetime(2026, 9, 7, 12, tzinfo=UTC)
    credential = build_role_credential(
        principal_id="reviewer-1",
        role=ReplicationSecurityRole.ANALYSIS_REVIEWER,
        public_key=public_key,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        issuer_id="test-issuer",
    )
    signing_payload = {
        "principal_id": credential.principal_id,
        "role": credential.role.value,
        "security_boundary_version": "8J.1.0",
        "signed_at": now,
        "subject_hash": "sha256:subject",
        "trusted_timestamp_token": "TEST_TIMESTAMP_TOKEN",
    }
    signature = private_key.sign(canonical_json(signing_payload).encode("utf-8"))
    identity = {**signing_payload, "signature": base64.b64encode(signature).decode("ascii")}
    attestation = SignedReplicationAttestation(
        deterministic_id("replication_attestation", identity),
        "sha256:subject",
        credential.principal_id,
        credential.role,
        now,
        "TEST_TIMESTAMP_TOKEN",
        base64.b64encode(signature).decode("ascii"),
    )
    assert verify_attestation(attestation, credential, lambda *_args: True)
    assert not verify_attestation(attestation, credential, lambda *_args: False)

    key = bytes(range(32))
    envelope = seal_outcome(
        collection_id="collection-1",
        prediction_id="prediction-1",
        key_id="test-key-1",
        key=key,
        outcome_payload={"net_r": "0.40"},
        sealed_at=now,
        nonce=b"0123456789ab",
        test_nonce_authorized=True,
    )
    assert "0.40" not in envelope.ciphertext_b64
    with pytest.raises(PermissionError, match="not authorized"):
        open_outcome(
            envelope,
            key=key,
            role=ReplicationSecurityRole.OUTCOME_STEWARD,
            frozen_dataset=True,
            release_authorized=True,
        )
    opened = open_outcome(
        envelope,
        key=key,
        role=ReplicationSecurityRole.ANALYSIS_REVIEWER,
        frozen_dataset=True,
        release_authorized=True,
    )
    assert opened == {"net_r": "0.40"}
    assert config.values["mode"] == "EXTERNAL_TRUST_INTERFACE_REFERENCE"


def test_security_config_and_access_chain_contract_fail_closed(tmp_path: Path) -> None:
    raw = json.loads(SECURITY_CONFIG.read_text(encoding="utf-8"))
    raw["authority"]["outcome_release_enabled"] = True
    path = tmp_path / "unsafe-security.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RangeReplicationSecurityConfigError, match="authority"):
        load_range_replication_security_config(path)
    event = build_access_event(
        principal_id="collector-1",
        role=ReplicationSecurityRole.COLLECTOR,
        action="APPEND_PREDICTION",
        subject_id="prediction-1",
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
        allowed=True,
        prior_event_hash=f"sha256:{'0' * 64}",
    )
    assert event.event_hash.startswith("sha256:")
    assert not event.production_authority
