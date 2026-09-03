"""Immutable Phase 6W artifact-trust proposal-catalog plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_proposal_catalog_plan_config import (
    ArtifactTrustProposalCatalogPlanConfig,
)
from trading_system.serialization import deterministic_id


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proposal catalog plan time must be timezone-aware")


@dataclass(frozen=True, slots=True, order=True)
class ArtifactTrustProposalCatalogPlanSource:
    proposal_id: str
    proposal_payload_hash: str

    def __post_init__(self) -> None:
        if not self.proposal_id:
            raise ValueError("planned proposal identity is required")
        _sha(self.proposal_payload_hash, "proposal payload hash")


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalCatalogPlan:
    plan_id: str
    registered_at: datetime
    sources: tuple[ArtifactTrustProposalCatalogPlanSource, ...]
    source_root_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.registered_at)
        _sha(self.source_root_hash, "planned source root")
        _sha(self.config_hash, "plan config hash")
        if not self.plan_id or not self.source_revision:
            raise ValueError("proposal catalog plan identity is required")
        if not self.sources or self.sources != tuple(sorted(set(self.sources))):
            raise ValueError("planned proposal sources must be unique and canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("plan disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        registered_at: datetime,
        sources: tuple[ArtifactTrustProposalCatalogPlanSource, ...],
        source_root_hash: str,
        source_revision: str,
        config: ArtifactTrustProposalCatalogPlanConfig,
    ) -> ArtifactTrustProposalCatalogPlan:
        disclosures = tuple(sorted((
            "PLAN_FREEZES_ONLY_A_LATER_CATALOG_MEMBERSHIP",
            "PROPOSALS_EXISTED_BEFORE_PLAN_AND_SELECTION_MAY_BE_BIASED",
            "PLAN_IS_LOCAL_UNSIGNED_AND_NOT_EXTERNALLY_TIMESTAMPED",
            "NO_AUTHENTICATION_CONSENSUS_POLICY_ACTIVATION_OR_TRADING_AUTHORITY",
        )))
        fields = (
            registered_at,
            sources,
            source_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(deterministic_id("artifact_trust_proposal_catalog_plan", fields), *fields)


class ArtifactTrustProposalCatalogReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    DEVIATION = "DEVIATION"
    MISSING = "MISSING"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalCatalogPlanReconciliation:
    reconciliation_id: str
    plan_id: str
    catalog_id: str
    reconciled_at: datetime
    status: ArtifactTrustProposalCatalogReconciliationStatus
    reasons: tuple[str, ...]
    plan_payload_hash: str
    catalog_payload_hash: str | None
    expected_proposal_count: int
    actual_proposal_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.reconciled_at)
        _sha(self.plan_payload_hash, "plan payload hash")
        _sha(self.config_hash, "plan config hash")
        if self.catalog_payload_hash is not None:
            _sha(self.catalog_payload_hash, "catalog payload hash")
        if not all((self.reconciliation_id, self.plan_id, self.catalog_id, self.source_revision)):
            raise ValueError("proposal catalog reconciliation identity is required")
        if self.expected_proposal_count <= 0 or self.actual_proposal_count < 0:
            raise ValueError("proposal catalog reconciliation counts are invalid")
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("reconciliation reasons must be canonical")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("reconciliation disclosures must be canonical")
        if (self.status is ArtifactTrustProposalCatalogReconciliationStatus.MATCHED) == bool(
            self.reasons
        ):
            raise ValueError("proposal catalog reconciliation status is inconsistent")

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
        expected_proposal_count: int,
        actual_proposal_count: int,
        source_revision: str,
        config: ArtifactTrustProposalCatalogPlanConfig,
    ) -> ArtifactTrustProposalCatalogPlanReconciliation:
        canonical = tuple(sorted(set(reasons)))
        status = (
            ArtifactTrustProposalCatalogReconciliationStatus.MISSING
            if missing
            else ArtifactTrustProposalCatalogReconciliationStatus.CORRUPT
            if corrupt
            else ArtifactTrustProposalCatalogReconciliationStatus.MATCHED
            if not canonical
            else ArtifactTrustProposalCatalogReconciliationStatus.DEVIATION
        )
        disclosures = tuple(sorted((
            "MATCHED_MEANS_EXACT_LATER_CATALOG_ADHERENCE_ONLY",
            "PLAN_DOES_NOT_PROVE_PROPOSAL_SELECTION_WAS_UNBIASED",
            "NO_CONSENSUS_POLICY_ACTIVATION_READINESS_OR_TRADING_INFERENCE",
        )))
        fields = (
            plan_id,
            catalog_id,
            reconciled_at,
            status,
            canonical,
            plan_payload_hash,
            catalog_payload_hash,
            expected_proposal_count,
            actual_proposal_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("artifact_trust_proposal_catalog_reconciliation", fields), *fields
        )
