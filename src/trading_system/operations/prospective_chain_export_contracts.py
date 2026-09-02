"""Immutable Phase 6K portable prospective-chain evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_export_config import ProspectiveChainExportConfig
from trading_system.serialization import deterministic_id


class ProspectiveChainVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProspectiveChainExportManifest:
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
            raise ValueError("export time must be timezone-aware")
        if self.artifact_bytes <= 0 or self.source_count <= 0:
            raise ValueError("export counts must be positive")
        for value in (self.artifact_hash, self.chain_root_hash, self.config_hash):
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError("export hashes must be SHA-256 identities")
        if not all(
            (
                self.export_id,
                self.materialization_id,
                self.artifact_path,
                self.source_revision,
                self.code_version,
            )
        ):
            raise ValueError("export identity is required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("export disclosures are invalid")

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
        config: ProspectiveChainExportConfig,
    ) -> ProspectiveChainExportManifest:
        disclosures = tuple(
            sorted(
                (
                    "LOCAL_UNSIGNED_UNENCRYPTED_ARTIFACT",
                    "NO_CONSENSUS_OR_PRODUCTION_READINESS_INFERENCE",
                    "NO_PROMOTION_BROKER_OR_LIVE_TRADING_AUTHORITY",
                )
            )
        )
        identity = (
            materialization_id,
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
            deterministic_id("prospective_chain_export", identity),
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
class ProspectiveChainExportVerification:
    verification_id: str
    export_id: str
    verified_at: datetime
    status: ProspectiveChainVerificationStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    promoted: bool
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("verification time must be timezone-aware")
        if self.promoted or self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("verification evidence is invalid")
        if (self.status is ProspectiveChainVerificationStatus.VERIFIED) is bool(self.reasons):
            raise ValueError("verification status is inconsistent")
        for value in (self.expected_hash, self.config_hash):
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError("verification hashes must be SHA-256 identities")

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
        config: ProspectiveChainExportConfig,
    ) -> ProspectiveChainExportVerification:
        canonical = tuple(sorted(set(reasons)))
        status = (
            ProspectiveChainVerificationStatus.VERIFIED
            if not canonical
            else ProspectiveChainVerificationStatus.FAILED
        )
        identity = (
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
        return cls(
            deterministic_id("prospective_chain_verification", identity),
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
