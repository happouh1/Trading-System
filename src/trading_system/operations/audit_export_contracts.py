"""Immutable Phase 6D portable audit-export evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_export_config import ObservationAuditExportConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class AuditExportVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class AuditExportManifest:
    export_id: str
    packet_id: str
    exported_at: datetime
    artifact_path: str
    artifact_hash: str
    artifact_bytes: int
    packet_payload_hash: str
    artifact_root_hash: str
    artifact_count: int
    reconciliation_status: str
    campaign_status: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.exported_at, "audit export timestamp")
        _sha(self.artifact_hash, "audit export artifact hash")
        _sha(self.packet_payload_hash, "audit export packet hash")
        _sha(self.artifact_root_hash, "audit export artifact root hash")
        if not all(
            (
                self.export_id,
                self.packet_id,
                self.artifact_path,
                self.reconciliation_status,
                self.campaign_status,
                self.source_revision,
                self.code_version,
                self.config_hash,
            )
        ):
            raise ValueError("audit export identity is required")
        if self.artifact_bytes <= 0 or self.artifact_count <= 0:
            raise ValueError("audit export must contain evidence")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("audit export disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        packet_id: str,
        exported_at: datetime,
        artifact_path: str,
        artifact_hash: str,
        artifact_bytes: int,
        packet_payload_hash: str,
        artifact_root_hash: str,
        artifact_count: int,
        reconciliation_status: str,
        campaign_status: str,
        source_revision: str,
        config: ObservationAuditExportConfig,
    ) -> AuditExportManifest:
        disclosures = tuple(
            sorted(
                (
                    "CONTENT_HASH_IS_NOT_AN_EXTERNAL_SIGNATURE",
                    "EXPORT_COMPLETENESS_IS_NOT_CAMPAIGN_SUCCESS",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_LOCAL_EVIDENCE_ONLY",
                    "SOURCE_STATUSES_RETAINED_WITHOUT_REINTERPRETATION",
                    "UNENCRYPTED_JSON_ARTIFACT",
                )
            )
        )
        identity = (
            packet_id,
            exported_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            packet_payload_hash,
            artifact_root_hash,
            artifact_count,
            reconciliation_status,
            campaign_status,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("observation_audit_export", identity),
            packet_id,
            exported_at,
            artifact_path,
            artifact_hash,
            artifact_bytes,
            packet_payload_hash,
            artifact_root_hash,
            artifact_count,
            reconciliation_status,
            campaign_status,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class AuditExportVerification:
    verification_id: str
    export_id: str
    verified_at: datetime
    status: AuditExportVerificationStatus
    expected_hash: str
    actual_hash: str | None
    reasons: tuple[str, ...]
    promoted: bool
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.verified_at, "audit export verification timestamp")
        _sha(self.expected_hash, "expected audit export hash")
        if self.actual_hash is not None:
            _sha(self.actual_hash, "actual audit export hash")
        if not all((self.verification_id, self.export_id, self.source_revision, self.code_version)):
            raise ValueError("audit export verification identity is required")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("audit export verification reasons must be canonical")
        if self.promoted:
            raise ValueError("Phase 6D verification cannot promote evidence")
        if (self.status is AuditExportVerificationStatus.VERIFIED) is bool(self.reasons):
            raise ValueError("audit export verification status is inconsistent")

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
        config: ObservationAuditExportConfig,
    ) -> AuditExportVerification:
        canonical_reasons = tuple(sorted(set(reasons)))
        status = (
            AuditExportVerificationStatus.VERIFIED
            if not canonical_reasons
            else AuditExportVerificationStatus.FAILED
        )
        identity = (
            export_id,
            verified_at,
            status,
            expected_hash,
            actual_hash,
            canonical_reasons,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("observation_audit_export_verification", identity),
            export_id,
            verified_at,
            status,
            expected_hash,
            actual_hash,
            canonical_reasons,
            False,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
