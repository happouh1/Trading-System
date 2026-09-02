"""Immutable Phase 6T local artifact-trust review export evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_review_export_config import (
    ArtifactTrustReviewExportConfig,
)
from trading_system.serialization import deterministic_id


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class ArtifactTrustReviewVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ArtifactTrustReviewExportManifest:
    export_id: str
    signing_request_id: str
    exported_at: datetime
    artifact_path: str
    artifact_hash: str
    artifact_bytes: int
    chain_root_hash: str
    source_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if self.exported_at.tzinfo is None or self.exported_at.utcoffset() is None:
            raise ValueError("trust review export time must be timezone-aware")
        for value, name in (
            (self.artifact_hash, "artifact hash"),
            (self.chain_root_hash, "chain root"),
            (self.config_hash, "config hash"),
        ):
            _sha(value, name)
        if self.artifact_bytes <= 0 or self.source_count != 4:
            raise ValueError("trust review export counts are invalid")
        if not all((self.export_id, self.signing_request_id, self.artifact_path)):
            raise ValueError("trust review export identity is required")
        if not self.source_revision:
            raise ValueError("trust review export provenance is required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("trust review export disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        signing_request_id: str,
        exported_at: datetime,
        artifact_path: str,
        artifact_hash: str,
        artifact_bytes: int,
        chain_root_hash: str,
        source_revision: str,
        config: ArtifactTrustReviewExportConfig,
    ) -> ArtifactTrustReviewExportManifest:
        disclosures = tuple(
            sorted(
                (
                    "HANDOFF_PACKET_IS_UNSIGNED_UNENCRYPTED_LOCAL_EVIDENCE",
                    "NO_KEYS_CREDENTIALS_SIGNATURES_OR_TRUSTED_TIMESTAMPS",
                    "NO_REVIEWER_AUTHENTICATION_CONSENSUS_OR_APPROVAL",
                    "NO_READINESS_PROMOTION_BROKERAGE_OR_TRADING_AUTHORITY",
                    "PHASE6R_6S_SOURCE_LINEAGE_RETAINED_EXACTLY",
                )
            )
        )
        identity = (
            signing_request_id,
            exported_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            chain_root_hash,
            4,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("artifact_trust_review_export", identity),
            signing_request_id,
            exported_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            chain_root_hash,
            4,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ArtifactTrustReviewExportVerification:
    verification_id: str
    export_id: str
    verified_at: datetime
    status: ArtifactTrustReviewVerificationStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    promoted: bool
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("trust review verification time must be timezone-aware")
        _sha(self.expected_hash, "expected hash")
        _sha(self.config_hash, "config hash")
        if self.actual_hash is not None:
            _sha(self.actual_hash, "actual hash")
        if self.promoted or self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("trust review verification evidence is invalid")
        verified = self.status is ArtifactTrustReviewVerificationStatus.VERIFIED
        if verified is bool(self.reasons):
            raise ValueError("trust review verification status is inconsistent")

    @classmethod
    def create(
        cls,
        *,
        export_id: str,
        verified_at: datetime,
        expected_hash: str,
        actual_hash: str | None,
        reasons: tuple[str, ...],
        source_revision: str,
        config: ArtifactTrustReviewExportConfig,
    ) -> ArtifactTrustReviewExportVerification:
        canonical = tuple(sorted(set(reasons)))
        status = (
            ArtifactTrustReviewVerificationStatus.VERIFIED
            if not canonical
            else ArtifactTrustReviewVerificationStatus.FAILED
        )
        identity = (
            export_id,
            verified_at,
            status,
            expected_hash,
            actual_hash,
            canonical,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("artifact_trust_review_verification", identity),
            export_id,
            verified_at,
            status,
            expected_hash,
            actual_hash,
            canonical,
            False,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
