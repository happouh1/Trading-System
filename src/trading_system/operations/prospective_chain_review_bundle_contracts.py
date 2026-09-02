"""Immutable Phase 6M portable prospective-chain review bundle evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_bundle_config import (
    ProspectiveChainReviewBundleConfig,
)
from trading_system.serialization import deterministic_id


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class ProspectiveReviewBundleVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProspectiveChainReviewBundleManifest:
    bundle_id: str
    export_id: str
    source_verification_id: str
    bundled_at: datetime
    artifact_path: str
    artifact_hash: str
    artifact_bytes: int
    export_manifest_hash: str
    source_verification_hash: str
    chain_root_hash: str
    review_root_hash: str
    review_count: int
    active_review_count: int
    summary_eligible_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if self.bundled_at.tzinfo is None or self.bundled_at.utcoffset() is None:
            raise ValueError("prospective review bundle timestamp must be timezone-aware")
        for value, name in (
            (self.artifact_hash, "bundle artifact hash"),
            (self.export_manifest_hash, "export manifest hash"),
            (self.source_verification_hash, "source verification hash"),
            (self.chain_root_hash, "chain root hash"),
            (self.review_root_hash, "review root hash"),
            (self.config_hash, "config hash"),
        ):
            _sha(value, name)
        if not all(
            (
                self.bundle_id,
                self.export_id,
                self.source_verification_id,
                self.artifact_path,
                self.source_revision,
                self.code_version,
            )
        ):
            raise ValueError("prospective review bundle identity is required")
        if self.artifact_bytes <= 0 or self.review_count <= 0:
            raise ValueError("prospective review bundle must contain review evidence")
        if not 0 <= self.summary_eligible_count <= self.active_review_count <= self.review_count:
            raise ValueError("prospective review bundle counts are invalid")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("prospective review bundle disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        export_id: str,
        source_verification_id: str,
        bundled_at: datetime,
        artifact_path: str,
        artifact_hash: str,
        artifact_bytes: int,
        export_manifest_hash: str,
        source_verification_hash: str,
        chain_root_hash: str,
        review_root_hash: str,
        review_count: int,
        active_review_count: int,
        summary_eligible_count: int,
        source_revision: str,
        config: ProspectiveChainReviewBundleConfig,
    ) -> ProspectiveChainReviewBundleManifest:
        disclosures = tuple(
            sorted(
                (
                    "CONTENT_HASH_IS_NOT_AN_EXTERNAL_SIGNATURE",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_CONSENSUS_OR_PRODUCTION_READINESS_RESULT",
                    "OFFLINE_LOCAL_UNSIGNED_UNENCRYPTED_EVIDENCE_ONLY",
                    "REVIEWER_IDENTITIES_ARE_UNAUTHENTICATED_ASSERTIONS",
                    "SOURCE_CHAIN_AND_ALL_REVIEW_HISTORY_RETAINED",
                )
            )
        )
        identity = (
            export_id,
            source_verification_id,
            bundled_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            export_manifest_hash,
            source_verification_hash,
            chain_root_hash,
            review_root_hash,
            review_count,
            active_review_count,
            summary_eligible_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_chain_review_bundle", identity),
            export_id,
            source_verification_id,
            bundled_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            export_manifest_hash,
            source_verification_hash,
            chain_root_hash,
            review_root_hash,
            review_count,
            active_review_count,
            summary_eligible_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ProspectiveChainReviewBundleVerification:
    verification_id: str
    bundle_id: str
    verified_at: datetime
    status: ProspectiveReviewBundleVerificationStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    promoted: bool
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("prospective review bundle verification time must be aware")
        _sha(self.expected_hash, "expected bundle hash")
        if self.actual_hash is not None:
            _sha(self.actual_hash, "actual bundle hash")
        if self.reasons != tuple(sorted(set(self.reasons))) or self.promoted:
            raise ValueError("prospective review bundle verification is invalid")
        if (self.status is ProspectiveReviewBundleVerificationStatus.VERIFIED) is bool(
            self.reasons
        ):
            raise ValueError("prospective review bundle verification status is inconsistent")

    @classmethod
    def create(
        cls,
        *,
        bundle_id: str,
        verified_at: datetime,
        expected_hash: str,
        actual_hash: str | None,
        reasons: tuple[str, ...],
        source_revision: str,
        config: ProspectiveChainReviewBundleConfig,
    ) -> ProspectiveChainReviewBundleVerification:
        canonical = tuple(sorted(set(reasons)))
        status = (
            ProspectiveReviewBundleVerificationStatus.VERIFIED
            if not canonical
            else ProspectiveReviewBundleVerificationStatus.FAILED
        )
        identity = (
            bundle_id,
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
            deterministic_id("prospective_chain_review_bundle_verification", identity),
            bundle_id,
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
