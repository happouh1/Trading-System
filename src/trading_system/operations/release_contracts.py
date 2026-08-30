"""Immutable Phase 5F release-evidence bundle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.release_config import OperationsReleaseConfig
from trading_system.serialization import deterministic_id


class ReleaseEvidenceStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ReleaseEvidenceBundle:
    bundle_id: str
    as_of: datetime
    readiness_manifest_id: str
    monitor_report_id: str
    control_snapshot_id: str
    run_request_id: str
    backup_id: str
    restore_verification_id: str
    status: ReleaseEvidenceStatus
    evidence_hashes: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]
    disclosures: tuple[str, ...]
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("release evidence as_of must be timezone-aware")
        identities = (
            self.bundle_id,
            self.readiness_manifest_id,
            self.monitor_report_id,
            self.control_snapshot_id,
            self.run_request_id,
            self.backup_id,
            self.restore_verification_id,
            self.source_revision,
            self.code_version,
            self.config_hash,
        )
        if not all(identities):
            raise ValueError("release evidence identities are required")
        if self.evidence_hashes != tuple(sorted(set(self.evidence_hashes))):
            raise ValueError("release evidence hashes must be canonical")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("release evidence reasons must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("release evidence disclosures must be canonical and nonempty")
        if (self.status is ReleaseEvidenceStatus.COMPLETE) is (bool(self.reasons)):
            raise ValueError("release evidence status and reasons are inconsistent")

    @classmethod
    def create(
        cls,
        *,
        as_of: datetime,
        readiness_manifest_id: str,
        monitor_report_id: str,
        control_snapshot_id: str,
        run_request_id: str,
        backup_id: str,
        restore_verification_id: str,
        evidence_hashes: tuple[tuple[str, str], ...],
        reasons: tuple[str, ...],
        source_revision: str,
        config: OperationsReleaseConfig,
    ) -> ReleaseEvidenceBundle:
        hashes = tuple(sorted(set(evidence_hashes)))
        canonical_reasons = tuple(sorted(set(reasons)))
        disclosures = tuple(
            sorted(
                (
                    "FRESHNESS_NOT_ASSESSED",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_PERSISTED_EVIDENCE_ONLY",
                )
            )
        )
        status = (
            ReleaseEvidenceStatus.COMPLETE
            if not canonical_reasons
            else ReleaseEvidenceStatus.INCOMPLETE
        )
        identity = (
            as_of,
            readiness_manifest_id,
            monitor_report_id,
            control_snapshot_id,
            run_request_id,
            backup_id,
            restore_verification_id,
            status,
            hashes,
            canonical_reasons,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("operations_release_bundle", identity),
            as_of,
            readiness_manifest_id,
            monitor_report_id,
            control_snapshot_id,
            run_request_id,
            backup_id,
            restore_verification_id,
            status,
            hashes,
            canonical_reasons,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
