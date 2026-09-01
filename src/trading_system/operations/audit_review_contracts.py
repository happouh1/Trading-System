"""Immutable Phase 6E independent-review assertions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_review_config import ObservationAuditReviewConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("audit review timestamp must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


class AuditReviewVerdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class ObservationAuditReview:
    review_id: str
    export_id: str
    verification_id: str
    reviewer_id: str
    reviewed_at: datetime
    verdict: AuditReviewVerdict
    reason_codes: tuple[str, ...]
    notes: str
    supersedes_review_id: str | None
    export_manifest_hash: str
    verification_payload_hash: str
    eligible_for_summary: bool
    reviewer_authenticated: bool
    promoted: bool
    disclosures: tuple[str, ...]
    source_revision: str
    code_version: str
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.reviewed_at)
        if not all(
            (
                self.review_id,
                self.export_id,
                self.verification_id,
                self.reviewer_id,
                self.source_revision,
                self.code_version,
                self.config_hash,
            )
        ):
            raise ValueError("audit review identity is required")
        _sha(self.export_manifest_hash, "export manifest hash")
        _sha(self.verification_payload_hash, "verification payload hash")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("audit review reason codes must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("audit review disclosures must be canonical")
        if self.eligible_for_summary is (self.verdict is AuditReviewVerdict.UNCERTAIN):
            raise ValueError("uncertain audit reviews cannot enter summaries")
        if self.reviewer_authenticated or self.promoted:
            raise ValueError("Phase 6E cannot authenticate reviewers or promote evidence")

    @classmethod
    def create(
        cls,
        *,
        export_id: str,
        verification_id: str,
        reviewer_id: str,
        reviewed_at: datetime,
        verdict: AuditReviewVerdict,
        reason_codes: tuple[str, ...],
        notes: str,
        supersedes_review_id: str | None,
        export_manifest_hash: str,
        verification_payload_hash: str,
        source_revision: str,
        config: ObservationAuditReviewConfig,
    ) -> ObservationAuditReview:
        canonical_reasons = tuple(sorted(set(reason_codes)))
        disclosures = tuple(
            sorted(
                (
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_CONSENSUS_OR_PRODUCTION_READINESS_RESULT",
                    "OFFLINE_APPEND_ONLY_REVIEW_ASSERTION",
                    "REVIEW_DOES_NOT_CHANGE_SOURCE_EVIDENCE",
                    "REVIEWER_IDENTITY_IS_UNAUTHENTICATED",
                    "UNCERTAIN_EXCLUDED_FROM_SUMMARY_COUNTS",
                )
            )
        )
        identity = (
            export_id,
            verification_id,
            reviewer_id,
            reviewed_at,
            verdict,
            canonical_reasons,
            notes,
            supersedes_review_id,
            export_manifest_hash,
            verification_payload_hash,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
        return cls(
            deterministic_id("observation_audit_review", identity),
            export_id,
            verification_id,
            reviewer_id,
            reviewed_at,
            verdict,
            canonical_reasons,
            notes,
            supersedes_review_id,
            export_manifest_hash,
            verification_payload_hash,
            verdict is not AuditReviewVerdict.UNCERTAIN,
            False,
            False,
            disclosures,
            source_revision,
            PACKAGE_VERSION,
            config.config_hash,
        )
