"""Immutable Phase 6Y prospective-plan catalog materialization evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_proposal_materialization_config import (
    ArtifactTrustProposalMaterializationConfig,
)
from trading_system.serialization import deterministic_id


class ArtifactTrustProposalMaterializationStatus(StrEnum):
    MATERIALIZED_DECLARED_SLOTS_ONLY = "MATERIALIZED_DECLARED_SLOTS_ONLY"


def _sha(value: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError("materialization hashes must be SHA-256 identities")


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalMaterialization:
    materialization_id: str
    source_plan_id: str
    catalog_id: str
    materialized_at: datetime
    cataloged_at: datetime
    proposal_ids: tuple[str, ...]
    slot_root_hash: str
    binding_root_hash: str
    plan_payload_hash: str
    catalog_payload_hash: str
    slot_count: int
    status: ArtifactTrustProposalMaterializationStatus
    complete_population_claim: bool
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if any(value.tzinfo is None or value.utcoffset() is None
               for value in (self.materialized_at, self.cataloged_at)):
            raise ValueError("materialization times must be timezone-aware")
        if self.cataloged_at <= self.materialized_at:
            raise ValueError("catalog time must follow materialization")
        for value in (self.slot_root_hash, self.binding_root_hash,
                      self.plan_payload_hash, self.catalog_payload_hash, self.config_hash):
            _sha(value)
        if not all((self.materialization_id, self.source_plan_id, self.catalog_id,
                    self.source_revision, self.code_version)):
            raise ValueError("materialization identity and provenance are required")
        if self.slot_count <= 0 or len(self.proposal_ids) != self.slot_count:
            raise ValueError("materialization proposal count must equal declared slot count")
        if self.proposal_ids != tuple(sorted(set(self.proposal_ids))):
            raise ValueError("materialized proposal IDs must be unique and canonical")
        if (
            self.status
            is not ArtifactTrustProposalMaterializationStatus.MATERIALIZED_DECLARED_SLOTS_ONLY
        ):
            raise ValueError("Phase 6Y status is invalid")
        if self.complete_population_claim:
            raise ValueError("Phase 6Y cannot claim a complete proposal population")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("materialization disclosures must be canonical")

    @classmethod
    def create(cls, *, source_plan_id: str, catalog_id: str,
               materialized_at: datetime, cataloged_at: datetime,
               proposal_ids: tuple[str, ...], slot_root_hash: str,
               binding_root_hash: str, plan_payload_hash: str,
               catalog_payload_hash: str, slot_count: int, source_revision: str,
               config: ArtifactTrustProposalMaterializationConfig
               ) -> ArtifactTrustProposalMaterialization:
        disclosures = tuple(sorted((
            "CATALOG_MEMBERSHIP_DERIVES_ONLY_FROM_PHASE6X_BINDINGS",
            "COMPLETE_MEANS_ALL_DECLARED_SLOTS_ONLY_NOT_ALL_POSSIBLE_PROPOSALS",
            "PROPOSALS_REMAIN_UNAUTHENTICATED_AND_POLICY_REMAINS_INACTIVE",
            "NO_CONSENSUS_READINESS_PROMOTION_OR_TRADING_AUTHORITY",
        )))
        fields = (
            source_plan_id, catalog_id, materialized_at, cataloged_at, proposal_ids,
            slot_root_hash, binding_root_hash, plan_payload_hash, catalog_payload_hash,
            slot_count,
            ArtifactTrustProposalMaterializationStatus.MATERIALIZED_DECLARED_SLOTS_ONLY,
            False, source_revision, PACKAGE_VERSION, disclosures, config.config_hash,
        )
        return cls(deterministic_id("artifact_trust_proposal_materialization", fields), *fields)
