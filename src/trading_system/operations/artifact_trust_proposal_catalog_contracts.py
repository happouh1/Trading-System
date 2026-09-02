"""Immutable Phase 6V descriptive catalogs of unauthenticated proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_proposal_catalog_config import (
    ArtifactTrustProposalCatalogConfig,
)
from trading_system.serialization import deterministic_id


class ArtifactTrustProposalCatalogStatus(StrEnum):
    ALL_VALUES_IDENTICAL_UNAUTHENTICATED = "ALL_VALUES_IDENTICAL_UNAUTHENTICATED"
    VALUES_DIFFER_UNAUTHENTICATED = "VALUES_DIFFER_UNAUTHENTICATED"


@dataclass(frozen=True, slots=True)
class PolicyFieldComparison:
    field_name: str
    proposal_values: tuple[tuple[str, str], ...]
    all_values_identical: bool

    def __post_init__(self) -> None:
        if not self.field_name or not self.proposal_values:
            raise ValueError("field comparison requires a name and values")
        if self.proposal_values != tuple(sorted(self.proposal_values)):
            raise ValueError("field comparison values must be canonical")
        if self.all_values_identical != (len({value for _, value in self.proposal_values}) == 1):
            raise ValueError("field comparison assessment is inconsistent")


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalCatalog:
    catalog_id: str
    review_export_id: str
    review_verification_id: str
    cataloged_at: datetime
    proposal_ids: tuple[str, ...]
    proposal_root_hash: str
    comparisons: tuple[PolicyFieldComparison, ...]
    status: ArtifactTrustProposalCatalogStatus
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if self.cataloged_at.tzinfo is None or self.cataloged_at.utcoffset() is None:
            raise ValueError("catalog time must be timezone-aware")
        if not self.proposal_ids or self.proposal_ids != tuple(sorted(set(self.proposal_ids))):
            raise ValueError("proposal IDs must be nonempty, sorted, and unique")
        if not self.proposal_root_hash.startswith("sha256:") or len(self.proposal_root_hash) != 71:
            raise ValueError("proposal root hash must be a SHA-256 identity")
        if not self.config_hash.startswith("sha256:") or len(self.config_hash) != 71:
            raise ValueError("config hash must be a SHA-256 identity")
        identical = all(item.all_values_identical for item in self.comparisons)
        expected = (
            ArtifactTrustProposalCatalogStatus.ALL_VALUES_IDENTICAL_UNAUTHENTICATED
            if identical
            else ArtifactTrustProposalCatalogStatus.VALUES_DIFFER_UNAUTHENTICATED
        )
        if self.status is not expected:
            raise ValueError("catalog status is inconsistent")
        if not all(
            (
                self.catalog_id,
                self.review_export_id,
                self.review_verification_id,
                self.source_revision,
                self.code_version,
            )
        ):
            raise ValueError("catalog identity and provenance are required")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("catalog disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        review_export_id: str,
        review_verification_id: str,
        cataloged_at: datetime,
        proposal_ids: tuple[str, ...],
        proposal_root_hash: str,
        comparisons: tuple[PolicyFieldComparison, ...],
        source_revision: str,
        config: ArtifactTrustProposalCatalogConfig,
    ) -> ArtifactTrustProposalCatalog:
        identical = all(item.all_values_identical for item in comparisons)
        status = (
            ArtifactTrustProposalCatalogStatus.ALL_VALUES_IDENTICAL_UNAUTHENTICATED
            if identical
            else ArtifactTrustProposalCatalogStatus.VALUES_DIFFER_UNAUTHENTICATED
        )
        disclosures = tuple(
            sorted(
                (
                    "FIELD_EQUALITY_IS_NOT_CONSENSUS_APPROVAL_OR_ACTIVE_POLICY",
                    "NO_PROPOSAL_SELECTED_RANKED_OR_PROMOTED",
                    "PROPOSAL_AUTHORS_AND_IDENTITIES_ARE_NOT_AUTHENTICATED",
                    "SOURCE_PHASE6T_VERIFICATION_RETAINED_EXACTLY",
                )
            )
        )
        fields = (
            review_export_id,
            review_verification_id,
            cataloged_at,
            proposal_ids,
            proposal_root_hash,
            comparisons,
            status,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(deterministic_id("artifact_trust_proposal_catalog", fields), *fields)
