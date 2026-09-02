"""Immutable Phase 6S trust-policy and blocked signing-request evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_config import ArtifactTrustConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("artifact trust time must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class ArtifactTrustPolicyStatus(StrEnum):
    BLOCKED_UNCONFIGURED = "BLOCKED_UNCONFIGURED"


class ArtifactSigningRequestStatus(StrEnum):
    BLOCKED_UNCONFIGURED = "BLOCKED_UNCONFIGURED"


BLOCKERS = tuple(
    sorted(
        (
            "ALGORITHM_UNRESOLVED",
            "KEY_CUSTODY_UNRESOLVED",
            "RECEIVING_VERIFIER_UNRESOLVED",
            "REVOCATION_POLICY_UNRESOLVED",
            "SIGNER_IDENTITY_UNRESOLVED",
            "TIMESTAMP_PROVIDER_UNRESOLVED",
        )
    )
)


@dataclass(frozen=True, slots=True)
class ArtifactTrustPolicy:
    policy_id: str
    registered_at: datetime
    status: ArtifactTrustPolicyStatus
    signature_algorithm: str
    key_custody: str
    signer_identity: str
    trusted_timestamp_provider: str
    revocation_policy: str
    receiving_verifier: str
    blockers: tuple[str, ...]
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.registered_at)
        _sha(self.config_hash, "artifact trust config hash")
        choices = (
            self.signature_algorithm,
            self.key_custody,
            self.signer_identity,
            self.trusted_timestamp_provider,
            self.revocation_policy,
            self.receiving_verifier,
        )
        if (
            self.status is not ArtifactTrustPolicyStatus.BLOCKED_UNCONFIGURED
            or set(choices) != {"UNRESOLVED"}
            or self.blockers != BLOCKERS
        ):
            raise ValueError("Phase 6S policy must remain explicitly unresolved")
        if not all((self.policy_id, self.source_revision, self.code_version)):
            raise ValueError("artifact trust policy identity is required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("artifact trust policy disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        registered_at: datetime,
        source_revision: str,
        config: ArtifactTrustConfig,
    ) -> ArtifactTrustPolicy:
        disclosures = tuple(
            sorted(
                (
                    "NO_KEY_MATERIAL_ACCEPTED_OR_STORED",
                    "NO_SIGNATURE_OR_TRUSTED_TIMESTAMP_CREATED",
                    "NO_TRUST_READINESS_PROMOTION_OR_TRADING_AUTHORITY",
                    "POLICY_RECORDS_UNRESOLVED_DECISIONS_ONLY",
                )
            )
        )
        identity = (
            registered_at,
            ArtifactTrustPolicyStatus.BLOCKED_UNCONFIGURED,
            config.signature_algorithm,
            config.key_custody,
            config.signer_identity,
            config.trusted_timestamp_provider,
            config.revocation_policy,
            config.receiving_verifier,
            BLOCKERS,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("artifact_trust_policy", identity),
            registered_at,
            ArtifactTrustPolicyStatus.BLOCKED_UNCONFIGURED,
            config.signature_algorithm,
            config.key_custody,
            config.signer_identity,
            config.trusted_timestamp_provider,
            config.revocation_policy,
            config.receiving_verifier,
            BLOCKERS,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ArtifactSigningRequest:
    request_id: str
    policy_id: str
    export_id: str
    export_verification_id: str
    requested_at: datetime
    status: ArtifactSigningRequestStatus
    artifact_hash: str
    chain_root_hash: str
    export_manifest_payload_hash: str
    export_verification_payload_hash: str
    blockers: tuple[str, ...]
    signed: bool
    trusted_timestamped: bool
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.requested_at)
        for value, name in (
            (self.artifact_hash, "artifact hash"),
            (self.chain_root_hash, "chain root"),
            (self.export_manifest_payload_hash, "export manifest payload hash"),
            (self.export_verification_payload_hash, "export verification payload hash"),
            (self.config_hash, "artifact trust config hash"),
        ):
            _sha(value, name)
        if (
            self.status is not ArtifactSigningRequestStatus.BLOCKED_UNCONFIGURED
            or self.blockers != BLOCKERS
            or self.signed
            or self.trusted_timestamped
        ):
            raise ValueError("Phase 6S signing request must remain blocked and unsigned")
        if not all((self.request_id, self.policy_id, self.export_id, self.export_verification_id)):
            raise ValueError("artifact signing request identity is required")
        if not all((self.source_revision, self.code_version)):
            raise ValueError("artifact signing request provenance is required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("artifact signing request disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        export_id: str,
        export_verification_id: str,
        requested_at: datetime,
        artifact_hash: str,
        chain_root_hash: str,
        export_manifest_payload_hash: str,
        export_verification_payload_hash: str,
        source_revision: str,
        config: ArtifactTrustConfig,
    ) -> ArtifactSigningRequest:
        disclosures = tuple(
            sorted(
                (
                    "BLOCKED_REQUEST_IS_NOT_A_SIGNATURE_OR_TIMESTAMP",
                    "NO_KEY_SECRET_CREDENTIAL_OR_NETWORK_USE",
                    "NO_READINESS_PROMOTION_BROKERAGE_OR_TRADING_AUTHORITY",
                    "SOURCE_PHASE6R_VERIFICATION_RETAINED_EXACTLY",
                )
            )
        )
        identity = (
            policy_id,
            export_id,
            export_verification_id,
            requested_at,
            artifact_hash,
            chain_root_hash,
            export_manifest_payload_hash,
            export_verification_payload_hash,
            BLOCKERS,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("artifact_signing_request", identity),
            policy_id,
            export_id,
            export_verification_id,
            requested_at,
            ArtifactSigningRequestStatus.BLOCKED_UNCONFIGURED,
            artifact_hash,
            chain_root_hash,
            export_manifest_payload_hash,
            export_verification_payload_hash,
            BLOCKERS,
            False,
            False,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
