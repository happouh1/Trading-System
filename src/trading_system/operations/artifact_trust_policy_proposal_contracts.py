"""Immutable Phase 6U unauthenticated artifact-trust policy proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_policy_proposal_config import (
    ArtifactTrustPolicyProposalConfig,
)
from trading_system.serialization import deterministic_id


class ArtifactTrustPolicyProposalStatus(StrEnum):
    PROPOSED_UNAUTHENTICATED = "PROPOSED_UNAUTHENTICATED"


POLICY_FIELDS = (
    "key_custody",
    "receiving_verifier",
    "revocation_policy",
    "signature_algorithm",
    "signer_identity",
    "trusted_timestamp_provider",
)


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


def _answer(value: str, name: str) -> None:
    if not value or value.strip() != value or value == "UNRESOLVED" or "\n" in value:
        raise ValueError(f"{name} proposal answer is invalid")
    prohibited = ("BEGIN PRIVATE KEY", "PRIVATE KEY-----", "APP_SECRET=", "TOKEN=")
    if any(marker in value.upper() for marker in prohibited):
        raise ValueError("secret or key material is forbidden")


@dataclass(frozen=True, slots=True)
class ArtifactTrustPolicyProposal:
    proposal_id: str
    review_export_id: str
    review_verification_id: str
    proposed_at: datetime
    status: ArtifactTrustPolicyProposalStatus
    signature_algorithm: str
    key_custody: str
    signer_identity: str
    trusted_timestamp_provider: str
    revocation_policy: str
    receiving_verifier: str
    review_artifact_hash: str
    review_chain_root_hash: str
    review_manifest_payload_hash: str
    review_verification_payload_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if self.proposed_at.tzinfo is None or self.proposed_at.utcoffset() is None:
            raise ValueError("policy proposal time must be timezone-aware")
        for value, name in (
            (self.review_artifact_hash, "review artifact hash"),
            (self.review_chain_root_hash, "review chain root"),
            (self.review_manifest_payload_hash, "review manifest payload hash"),
            (self.review_verification_payload_hash, "review verification payload hash"),
            (self.config_hash, "config hash"),
        ):
            _sha(value, name)
        for value, name in zip(self.answers, POLICY_FIELDS, strict=True):
            _answer(value, name)
        if self.status is not ArtifactTrustPolicyProposalStatus.PROPOSED_UNAUTHENTICATED:
            raise ValueError("Phase 6U proposal must remain unauthenticated")
        if not all(
            (
                self.proposal_id,
                self.review_export_id,
                self.review_verification_id,
                self.source_revision,
                self.code_version,
            )
        ):
            raise ValueError("policy proposal identity and provenance are required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("policy proposal disclosures must be canonical")

    @property
    def answers(self) -> tuple[str, ...]:
        return (
            self.key_custody,
            self.receiving_verifier,
            self.revocation_policy,
            self.signature_algorithm,
            self.signer_identity,
            self.trusted_timestamp_provider,
        )

    @classmethod
    def create(
        cls,
        *,
        review_export_id: str,
        review_verification_id: str,
        proposed_at: datetime,
        signature_algorithm: str,
        key_custody: str,
        signer_identity: str,
        trusted_timestamp_provider: str,
        revocation_policy: str,
        receiving_verifier: str,
        review_artifact_hash: str,
        review_chain_root_hash: str,
        review_manifest_payload_hash: str,
        review_verification_payload_hash: str,
        source_revision: str,
        config: ArtifactTrustPolicyProposalConfig,
    ) -> ArtifactTrustPolicyProposal:
        disclosures = tuple(
            sorted(
                (
                    "ANSWERS_ARE_UNAUTHENTICATED_PROPOSALS_NOT_ACTIVE_POLICY",
                    "NO_KEY_SECRET_CREDENTIAL_SIGNATURE_OR_TRUSTED_TIMESTAMP",
                    "NO_REVIEW_APPROVAL_CONSENSUS_OR_IDENTITY_AUTHENTICATION",
                    "NO_READINESS_PROMOTION_BROKERAGE_OR_TRADING_AUTHORITY",
                    "SOURCE_PHASE6T_VERIFICATION_RETAINED_EXACTLY",
                )
            )
        )
        fields = (
            review_export_id,
            review_verification_id,
            proposed_at,
            ArtifactTrustPolicyProposalStatus.PROPOSED_UNAUTHENTICATED,
            signature_algorithm,
            key_custody,
            signer_identity,
            trusted_timestamp_provider,
            revocation_policy,
            receiving_verifier,
            review_artifact_hash,
            review_chain_root_hash,
            review_manifest_payload_hash,
            review_verification_payload_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(deterministic_id("artifact_trust_policy_proposal", fields), *fields)
