"""Immutable Phase 6N verified prospective-chain review bundle catalogs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_catalog_config import (
    ProspectiveChainReviewCatalogConfig,
)
from trading_system.serialization import deterministic_id


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


@dataclass(frozen=True, slots=True)
class ProspectiveChainReviewCatalogEntry:
    bundle_id: str
    verification_id: str
    artifact_hash: str
    manifest_payload_hash: str
    verification_payload_hash: str
    chain_root_hash: str
    review_root_hash: str
    review_count: int
    active_review_count: int
    summary_eligible_count: int
    verified_at: datetime

    def __post_init__(self) -> None:
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("catalog entry verification time must be timezone-aware")
        for value, name in (
            (self.artifact_hash, "bundle artifact hash"),
            (self.manifest_payload_hash, "bundle manifest hash"),
            (self.verification_payload_hash, "bundle verification hash"),
            (self.chain_root_hash, "chain root hash"),
            (self.review_root_hash, "review root hash"),
        ):
            _sha(value, name)
        if not self.bundle_id or not self.verification_id or self.review_count <= 0:
            raise ValueError("prospective review catalog entry identity is required")
        if not 0 <= self.summary_eligible_count <= self.active_review_count <= self.review_count:
            raise ValueError("prospective review catalog entry counts are invalid")


@dataclass(frozen=True, slots=True)
class ProspectiveChainReviewCatalog:
    catalog_id: str
    catalog_name: str
    cataloged_at: datetime
    entries: tuple[ProspectiveChainReviewCatalogEntry, ...]
    catalog_root_hash: str
    bundle_count: int
    total_review_count: int
    total_active_review_count: int
    total_summary_eligible_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if self.cataloged_at.tzinfo is None or self.cataloged_at.utcoffset() is None:
            raise ValueError("prospective review catalog time must be timezone-aware")
        _sha(self.catalog_root_hash, "prospective review catalog root")
        if not all((self.catalog_id, self.catalog_name, self.source_revision, self.config_hash)):
            raise ValueError("prospective review catalog identity is required")
        if not self.entries or self.bundle_count != len(self.entries):
            raise ValueError("prospective review catalog must contain explicit entries")
        if tuple(entry.bundle_id for entry in self.entries) != tuple(
            sorted({entry.bundle_id for entry in self.entries})
        ):
            raise ValueError("prospective review catalog entries must be unique and canonical")
        expected = (
            sum(entry.review_count for entry in self.entries),
            sum(entry.active_review_count for entry in self.entries),
            sum(entry.summary_eligible_count for entry in self.entries),
        )
        if expected != (
            self.total_review_count,
            self.total_active_review_count,
            self.total_summary_eligible_count,
        ):
            raise ValueError("prospective review catalog totals mismatch")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("prospective review catalog disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        catalog_name: str,
        cataloged_at: datetime,
        entries: tuple[ProspectiveChainReviewCatalogEntry, ...],
        catalog_root_hash: str,
        source_revision: str,
        config: ProspectiveChainReviewCatalogConfig,
    ) -> ProspectiveChainReviewCatalog:
        disclosures = tuple(
            sorted(
                (
                    "BUNDLE_SELECTION_IS_CALLER_DECLARED",
                    "CATALOG_COUNTS_ARE_NOT_CONSENSUS_OR_RANKING",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NOT_A_PRODUCTION_READINESS_CLAIM",
                    "OFFLINE_APPEND_ONLY_EVIDENCE_ONLY",
                    "REVIEWER_IDENTITIES_REMAIN_UNAUTHENTICATED",
                )
            )
        )
        identity = (
            catalog_name,
            cataloged_at,
            entries,
            catalog_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_chain_review_catalog", identity),
            catalog_name,
            cataloged_at,
            entries,
            catalog_root_hash,
            len(entries),
            sum(entry.review_count for entry in entries),
            sum(entry.active_review_count for entry in entries),
            sum(entry.summary_eligible_count for entry in entries),
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
