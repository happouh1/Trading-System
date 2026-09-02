"""Immutable Phase 6H review-catalog plans and reconciliation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_review_plan_config import ReviewCatalogPlanConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review catalog plan timestamp must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


@dataclass(frozen=True, slots=True, order=True)
class ReviewCatalogPlanSource:
    bundle_id: str
    verification_id: str

    def __post_init__(self) -> None:
        if not self.bundle_id or not self.verification_id:
            raise ValueError("planned review bundle identity is required")


@dataclass(frozen=True, slots=True)
class ReviewCatalogPlan:
    plan_id: str
    catalog_name: str
    registered_at: datetime
    sources: tuple[ReviewCatalogPlanSource, ...]
    source_root_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.registered_at)
        _sha(self.source_root_hash, "planned source root hash")
        _sha(self.config_hash, "review catalog plan configuration hash")
        if not self.plan_id or not self.catalog_name or not self.source_revision:
            raise ValueError("review catalog plan identity is required")
        if not self.sources or self.sources != tuple(sorted(set(self.sources))):
            raise ValueError("planned review sources must be unique and canonical")
        if len({source.bundle_id for source in self.sources}) != len(self.sources):
            raise ValueError("planned bundle IDs must be unique")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("review catalog plan disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        catalog_name: str,
        registered_at: datetime,
        sources: tuple[ReviewCatalogPlanSource, ...],
        source_root_hash: str,
        source_revision: str,
        config: ReviewCatalogPlanConfig,
    ) -> ReviewCatalogPlan:
        disclosures = tuple(
            sorted(
                (
                    "BUNDLE_IDENTITIES_MAY_ENCODE_ALREADY_KNOWN_REVIEW_HISTORY",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_CONSENSUS_OR_PRODUCTION_READINESS_RESULT",
                    "PLAN_FREEZES_ONLY_THE_LATER_CATALOG_DENOMINATOR",
                    "REVIEWER_IDENTITIES_REMAIN_UNAUTHENTICATED",
                )
            )
        )
        identity = (
            catalog_name,
            registered_at,
            sources,
            source_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("review_catalog_plan", identity),
            catalog_name,
            registered_at,
            sources,
            source_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


class ReviewCatalogReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    DEVIATION = "DEVIATION"
    MISSING = "MISSING"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class ReviewCatalogPlanReconciliation:
    reconciliation_id: str
    plan_id: str
    catalog_id: str
    reconciled_at: datetime
    status: ReviewCatalogReconciliationStatus
    reasons: tuple[str, ...]
    plan_payload_hash: str
    catalog_payload_hash: str | None
    expected_bundle_count: int
    actual_bundle_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.reconciled_at)
        _sha(self.plan_payload_hash, "plan payload hash")
        _sha(self.config_hash, "review catalog reconciliation configuration hash")
        if self.catalog_payload_hash is not None:
            _sha(self.catalog_payload_hash, "catalog payload hash")
        if not all(
            (
                self.reconciliation_id,
                self.plan_id,
                self.catalog_id,
                self.source_revision,
                self.code_version,
            )
        ):
            raise ValueError("review catalog reconciliation identity is required")
        if self.expected_bundle_count <= 0 or self.actual_bundle_count < 0:
            raise ValueError("review catalog reconciliation counts are invalid")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("reconciliation reasons must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("review catalog reconciliation disclosures must be canonical")
        if (self.status is ReviewCatalogReconciliationStatus.MATCHED) is bool(self.reasons):
            raise ValueError("review catalog reconciliation status is inconsistent")

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        catalog_id: str,
        reconciled_at: datetime,
        reasons: tuple[str, ...],
        missing: bool,
        corrupt: bool,
        plan_payload_hash: str,
        catalog_payload_hash: str | None,
        expected_bundle_count: int,
        actual_bundle_count: int,
        source_revision: str,
        config: ReviewCatalogPlanConfig,
    ) -> ReviewCatalogPlanReconciliation:
        canonical_reasons = tuple(sorted(set(reasons)))
        status = (
            ReviewCatalogReconciliationStatus.MISSING
            if missing
            else ReviewCatalogReconciliationStatus.CORRUPT
            if corrupt
            else ReviewCatalogReconciliationStatus.MATCHED
            if not canonical_reasons
            else ReviewCatalogReconciliationStatus.DEVIATION
        )
        disclosures = tuple(
            sorted(
                (
                    "MATCHED_MEANS_EXACT_CATALOG_ADHERENCE_ONLY",
                    "NO_CONSENSUS_OR_PRODUCTION_READINESS_INFERENCE",
                    "NO_TRADING_OR_PROMOTION_AUTHORITY",
                    "PLAN_DOES_NOT_PROVE_INITIAL_SELECTION_WAS_UNBIASED",
                )
            )
        )
        identity = (
            plan_id,
            catalog_id,
            reconciled_at,
            status,
            canonical_reasons,
            plan_payload_hash,
            catalog_payload_hash,
            expected_bundle_count,
            actual_bundle_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("review_catalog_plan_reconciliation", identity),
            plan_id,
            catalog_id,
            reconciled_at,
            status,
            canonical_reasons,
            plan_payload_hash,
            catalog_payload_hash,
            expected_bundle_count,
            actual_bundle_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
