"""Immutable Phase 6R portable materialization-chain evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_review_bundle_chain_export_config import (
    ProspectiveReviewBundleChainExportConfig,
)
from trading_system.serialization import deterministic_id


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class ProspectiveReviewBundleChainVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundleChainExportManifest:
    export_id: str
    materialization_id: str
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
            raise ValueError("chain export time must be timezone-aware")
        for value, name in (
            (self.artifact_hash, "artifact hash"),
            (self.chain_root_hash, "chain root"),
            (self.config_hash, "config hash"),
        ):
            _sha(value, name)
        if self.artifact_bytes <= 0 or self.source_count <= 0:
            raise ValueError("chain export counts must be positive")
        if not all(
            (self.export_id, self.materialization_id, self.artifact_path, self.source_revision)
        ):
            raise ValueError("chain export identity is required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("chain export disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        materialization_id: str,
        exported_at: datetime,
        artifact_path: str,
        artifact_hash: str,
        artifact_bytes: int,
        chain_root_hash: str,
        source_count: int,
        source_revision: str,
        config: ProspectiveReviewBundleChainExportConfig,
    ) -> ProspectiveReviewBundleChainExportManifest:
        disclosures = tuple(
            sorted(
                (
                    "CONTENT_HASH_IS_NOT_AN_EXTERNAL_SIGNATURE",
                    "NO_CONSENSUS_READINESS_PROMOTION_OR_TRADING_AUTHORITY",
                    "OFFLINE_LOCAL_UNSIGNED_UNENCRYPTED_EVIDENCE_ONLY",
                    "PHASE6P_6O_6N_6Q_SOURCE_CHAIN_RETAINED",
                    "TIMESTAMPS_AND_IDENTITIES_ARE_NOT_EXTERNALLY_AUTHENTICATED",
                )
            )
        )
        identity = (
            materialization_id,
            exported_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            chain_root_hash,
            source_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_review_bundle_chain_export", identity),
            materialization_id,
            exported_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            chain_root_hash,
            source_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundleChainExportVerification:
    verification_id: str
    export_id: str
    verified_at: datetime
    status: ProspectiveReviewBundleChainVerificationStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    promoted: bool
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("chain verification time must be timezone-aware")
        _sha(self.expected_hash, "expected hash")
        _sha(self.config_hash, "config hash")
        if self.actual_hash is not None:
            _sha(self.actual_hash, "actual hash")
        if self.promoted or self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("chain verification evidence is invalid")
        if (self.status is ProspectiveReviewBundleChainVerificationStatus.VERIFIED) is bool(
            self.reasons
        ):
            raise ValueError("chain verification status is inconsistent")

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
        config: ProspectiveReviewBundleChainExportConfig,
    ) -> ProspectiveReviewBundleChainExportVerification:
        canonical = tuple(sorted(set(reasons)))
        status = (
            ProspectiveReviewBundleChainVerificationStatus.VERIFIED
            if not canonical
            else ProspectiveReviewBundleChainVerificationStatus.FAILED
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
            deterministic_id("prospective_review_bundle_chain_verification", identity),
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
