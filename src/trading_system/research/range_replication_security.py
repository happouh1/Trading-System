"""Phase 8J cryptographic interfaces for a future separated replication boundary."""

from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from trading_system.serialization import canonical_hash, canonical_json, deterministic_id


class RangeReplicationSecurityConfigError(ValueError):
    pass


class ReplicationSecurityRole(StrEnum):
    COLLECTOR = "COLLECTOR"
    OUTCOME_STEWARD = "OUTCOME_STEWARD"
    ANALYSIS_REVIEWER = "ANALYSIS_REVIEWER"
    SECURITY_AUDITOR = "SECURITY_AUDITOR"


@dataclass(frozen=True, slots=True)
class RangeReplicationSecurityConfig:
    values: Mapping[str, object]
    config_hash: str


@dataclass(frozen=True, slots=True)
class ReplicationRoleCredential:
    credential_id: str
    principal_id: str
    role: ReplicationSecurityRole
    public_key_b64: str
    valid_from: datetime
    valid_until: datetime
    issuer_id: str
    security_boundary_version: str = "8J.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        try:
            public_key = base64.b64decode(self.public_key_b64, validate=True)
        except ValueError as exc:
            raise ValueError("invalid Phase 8J public key encoding") from exc
        if (
            not all((self.credential_id, self.principal_id, self.issuer_id))
            or len(public_key) != 32
            or not _is_utc(self.valid_from)
            or not _is_utc(self.valid_until)
            or self.valid_from >= self.valid_until
            or self.security_boundary_version != "8J.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8J role credential")


@dataclass(frozen=True, slots=True)
class SignedReplicationAttestation:
    attestation_id: str
    subject_hash: str
    principal_id: str
    role: ReplicationSecurityRole
    signed_at: datetime
    trusted_timestamp_token: str
    signature_b64: str
    security_boundary_version: str = "8J.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        try:
            signature = base64.b64decode(self.signature_b64, validate=True)
        except ValueError as exc:
            raise ValueError("invalid Phase 8J signature encoding") from exc
        if (
            not self.attestation_id
            or not _is_hash(self.subject_hash)
            or not self.principal_id
            or not _is_utc(self.signed_at)
            or not self.trusted_timestamp_token
            or len(signature) != 64
            or self.security_boundary_version != "8J.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8J signed attestation")

    def signing_payload(self) -> Mapping[str, object]:
        return {
            "principal_id": self.principal_id,
            "role": self.role.value,
            "security_boundary_version": self.security_boundary_version,
            "signed_at": self.signed_at,
            "subject_hash": self.subject_hash,
            "trusted_timestamp_token": self.trusted_timestamp_token,
        }


@dataclass(frozen=True, slots=True)
class SealedReplicationOutcome:
    envelope_id: str
    collection_id: str
    prediction_id: str
    key_id: str
    nonce_b64: str
    ciphertext_b64: str
    associated_data_hash: str
    sealed_at: datetime
    security_boundary_version: str = "8J.1.0"
    plaintext_persisted: bool = False
    released_for_analysis: bool = False
    production_authority: bool = False

    def __post_init__(self) -> None:
        try:
            nonce = base64.b64decode(self.nonce_b64, validate=True)
            ciphertext = base64.b64decode(self.ciphertext_b64, validate=True)
        except ValueError as exc:
            raise ValueError("invalid Phase 8J outcome envelope encoding") from exc
        if (
            not all((self.envelope_id, self.collection_id, self.prediction_id, self.key_id))
            or len(nonce) != 12
            or len(ciphertext) < 17
            or not _is_hash(self.associated_data_hash)
            or not _is_utc(self.sealed_at)
            or self.security_boundary_version != "8J.1.0"
            or self.plaintext_persisted
            or self.released_for_analysis
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8J sealed outcome")


@dataclass(frozen=True, slots=True)
class ReplicationAccessEvent:
    event_id: str
    principal_id: str
    role: ReplicationSecurityRole
    action: str
    subject_id: str
    occurred_at: datetime
    allowed: bool
    prior_event_hash: str
    event_hash: str
    security_boundary_version: str = "8J.1.0"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not all((self.event_id, self.principal_id, self.action, self.subject_id))
            or not _is_utc(self.occurred_at)
            or not _is_hash(self.prior_event_hash)
            or not _is_hash(self.event_hash)
            or self.security_boundary_version != "8J.1.0"
            or self.production_authority
        ):
            raise ValueError("invalid Phase 8J access event")


TrustedTimestampVerifier = Callable[[str, str, datetime], bool]


def load_range_replication_security_config(
    path: str | Path,
) -> RangeReplicationSecurityConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "security_boundary_version",
        "mode",
        "algorithms",
        "role_policy",
        "authority",
    }:
        raise RangeReplicationSecurityConfigError("Phase 8J configuration keys are invalid")
    if (
        raw["security_boundary_version"] != "8J.1.0"
        or raw["mode"] != "EXTERNAL_TRUST_INTERFACE_REFERENCE"
        or raw["algorithms"]
        != {
            "content_hash": "SHA-256",
            "signature": "Ed25519",
            "outcome_encryption": "AES-256-GCM",
        }
        or raw["role_policy"]
        != {
            "required_roles": ["COLLECTOR", "OUTCOME_STEWARD", "ANALYSIS_REVIEWER"],
            "distinct_principals": True,
            "least_privilege": True,
            "append_only_access_log": True,
            "trusted_timestamp_required": True,
        }
    ):
        raise RangeReplicationSecurityConfigError("Phase 8J security policy is invalid")
    authority = raw["authority"]
    expected_authority = {
        "external_trust_service_configured",
        "real_blinding_attested",
        "outcome_release_enabled",
        "analysis_enabled",
        "efficacy_claims_enabled",
        "parameter_selection_enabled",
        "alerts_enabled",
        "broker_writes_enabled",
        "live_trading_enabled",
    }
    if (
        not isinstance(authority, dict)
        or set(authority) != expected_authority
        or any(value is not False for value in authority.values())
    ):
        raise RangeReplicationSecurityConfigError("Phase 8J authority must remain disabled")
    frozen = {key: _freeze_value(value) for key, value in raw.items()}
    return RangeReplicationSecurityConfig(MappingProxyType(frozen), canonical_hash(raw))


def build_role_credential(
    *,
    principal_id: str,
    role: ReplicationSecurityRole,
    public_key: bytes,
    valid_from: datetime,
    valid_until: datetime,
    issuer_id: str,
) -> ReplicationRoleCredential:
    if not _is_utc(valid_from) or not _is_utc(valid_until):
        raise ValueError("Phase 8J credential timestamps must be UTC")
    core = {
        "principal_id": principal_id,
        "role": role.value,
        "public_key_b64": base64.b64encode(public_key).decode("ascii"),
        "valid_from": valid_from,
        "valid_until": valid_until,
        "issuer_id": issuer_id,
        "security_boundary_version": "8J.1.0",
    }
    return ReplicationRoleCredential(
        deterministic_id("replication_role_credential", core),
        principal_id,
        role,
        str(core["public_key_b64"]),
        valid_from.astimezone(UTC),
        valid_until.astimezone(UTC),
        issuer_id,
    )


def verify_attestation(
    attestation: SignedReplicationAttestation,
    credential: ReplicationRoleCredential,
    timestamp_verifier: TrustedTimestampVerifier,
) -> bool:
    if (
        attestation.principal_id != credential.principal_id
        or attestation.role is not credential.role
        or not credential.valid_from <= attestation.signed_at < credential.valid_until
        or not timestamp_verifier(
            attestation.trusted_timestamp_token,
            attestation.subject_hash,
            attestation.signed_at,
        )
    ):
        return False
    public_key = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(credential.public_key_b64, validate=True)
    )
    try:
        public_key.verify(
            base64.b64decode(attestation.signature_b64, validate=True),
            canonical_json(attestation.signing_payload()).encode("utf-8"),
        )
    except InvalidSignature:
        return False
    return True


def seal_outcome(
    *,
    collection_id: str,
    prediction_id: str,
    key_id: str,
    key: bytes,
    outcome_payload: Mapping[str, object],
    sealed_at: datetime,
    nonce: bytes | None = None,
    test_nonce_authorized: bool = False,
) -> SealedReplicationOutcome:
    if len(key) != 32:
        raise ValueError("Phase 8J outcome encryption requires a 256-bit key")
    if nonce is not None and not test_nonce_authorized:
        raise ValueError("caller-supplied Phase 8J nonces are test-only")
    actual_nonce = os.urandom(12) if nonce is None else nonce
    if len(actual_nonce) != 12:
        raise ValueError("Phase 8J AES-GCM nonce must contain 12 bytes")
    associated_data = {
        "collection_id": collection_id,
        "prediction_id": prediction_id,
        "key_id": key_id,
        "sealed_at": sealed_at,
        "security_boundary_version": "8J.1.0",
    }
    associated_json = canonical_json(associated_data).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(
        actual_nonce,
        canonical_json(outcome_payload).encode("utf-8"),
        associated_json,
    )
    core = {
        **associated_data,
        "nonce_b64": base64.b64encode(actual_nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "associated_data_hash": canonical_hash(associated_data),
    }
    return SealedReplicationOutcome(
        deterministic_id("sealed_replication_outcome", core),
        collection_id,
        prediction_id,
        key_id,
        str(core["nonce_b64"]),
        str(core["ciphertext_b64"]),
        str(core["associated_data_hash"]),
        sealed_at.astimezone(UTC),
    )


def open_outcome(
    envelope: SealedReplicationOutcome,
    *,
    key: bytes,
    role: ReplicationSecurityRole,
    frozen_dataset: bool,
    release_authorized: bool,
) -> Mapping[str, object]:
    if (
        role is not ReplicationSecurityRole.ANALYSIS_REVIEWER
        or not frozen_dataset
        or not release_authorized
    ):
        raise PermissionError("Phase 8J outcome release is not authorized")
    associated_data = {
        "collection_id": envelope.collection_id,
        "prediction_id": envelope.prediction_id,
        "key_id": envelope.key_id,
        "sealed_at": envelope.sealed_at,
        "security_boundary_version": envelope.security_boundary_version,
    }
    if canonical_hash(associated_data) != envelope.associated_data_hash:
        raise ValueError("Phase 8J associated data is corrupt")
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(envelope.nonce_b64, validate=True),
        base64.b64decode(envelope.ciphertext_b64, validate=True),
        canonical_json(associated_data).encode("utf-8"),
    )
    decoded = json.loads(plaintext)
    if not isinstance(decoded, dict):
        raise ValueError("Phase 8J outcome plaintext must be an object")
    return MappingProxyType(decoded)


def build_access_event(
    *,
    principal_id: str,
    role: ReplicationSecurityRole,
    action: str,
    subject_id: str,
    occurred_at: datetime,
    allowed: bool,
    prior_event_hash: str,
) -> ReplicationAccessEvent:
    core = {
        "principal_id": principal_id,
        "role": role.value,
        "action": action,
        "subject_id": subject_id,
        "occurred_at": occurred_at,
        "allowed": allowed,
        "prior_event_hash": prior_event_hash,
        "security_boundary_version": "8J.1.0",
    }
    event_hash = canonical_hash(core)
    return ReplicationAccessEvent(
        deterministic_id("replication_access_event", core),
        principal_id,
        role,
        action,
        subject_id,
        occurred_at.astimezone(UTC),
        allowed,
        prior_event_hash,
        event_hash,
    )


def _is_hash(value: str) -> bool:
    return value.startswith("sha256:") and len(value) > len("sha256:")


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


def _freeze_value(value: object) -> object:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise RangeReplicationSecurityConfigError("Phase 8J config keys must be strings")
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value
