"""Immutable Phase 6X prospective proposal slots and bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_proposal_plan_config import (
    ArtifactTrustProposalPlanConfig,
)
from trading_system.serialization import deterministic_id


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proposal plan timestamp must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


@dataclass(frozen=True, slots=True, order=True)
class ArtifactTrustProposalSlot:
    slot_id: str
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        _aware(self.opens_at)
        _aware(self.closes_at)
        if not self.slot_id:
            raise ValueError("proposal slot ID is required")
        if self.opens_at >= self.closes_at:
            raise ValueError("proposal slot window must have positive duration")


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalPlan:
    plan_id: str
    plan_name: str
    review_export_id: str
    review_verification_id: str
    registered_at: datetime
    slots: tuple[ArtifactTrustProposalSlot, ...]
    slot_root_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.registered_at)
        _sha(self.slot_root_hash, "proposal slot root")
        _sha(self.config_hash, "proposal plan config hash")
        if not all((self.plan_id, self.plan_name, self.review_export_id,
                    self.review_verification_id, self.source_revision, self.code_version)):
            raise ValueError("proposal plan identity and provenance are required")
        if not self.slots or self.registered_at >= min(item.opens_at for item in self.slots):
            raise ValueError("plan registration must precede every proposal window")
        if self.slots != tuple(sorted(set(self.slots))):
            raise ValueError("proposal slots must be unique and canonical")
        if len({item.slot_id for item in self.slots}) != len(self.slots) or len(
            {(item.opens_at, item.closes_at) for item in self.slots}
        ) != len(self.slots):
            raise ValueError("proposal slot IDs and windows must be unique")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("proposal plan disclosures must be canonical")

    @classmethod
    def create(cls, *, plan_name: str, review_export_id: str,
               review_verification_id: str, registered_at: datetime,
               slots: tuple[ArtifactTrustProposalSlot, ...], slot_root_hash: str,
               source_revision: str, config: ArtifactTrustProposalPlanConfig
               ) -> ArtifactTrustProposalPlan:
        disclosures = tuple(sorted((
            "DECLARED_SLOTS_DO_NOT_PROVE_A_COMPLETE_PROPOSAL_POPULATION",
            "PROPOSAL_CONTENT_IDENTITIES_ARE_UNKNOWN_AT_REGISTRATION",
            "PLAN_IS_LOCAL_UNSIGNED_AND_NOT_EXTERNALLY_TIMESTAMPED",
            "NO_AUTHENTICATION_CONSENSUS_POLICY_ACTIVATION_OR_TRADING_AUTHORITY",
        )))
        fields = (plan_name, review_export_id, review_verification_id, registered_at, slots,
                  slot_root_hash, source_revision, PACKAGE_VERSION, disclosures,
                  config.config_hash)
        return cls(deterministic_id("artifact_trust_proposal_plan", fields), *fields)


@dataclass(frozen=True, slots=True)
class ArtifactTrustProposalBinding:
    binding_id: str
    plan_id: str
    slot_id: str
    proposal_id: str
    bound_at: datetime
    proposed_at: datetime
    proposal_payload_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.bound_at)
        _aware(self.proposed_at)
        _sha(self.proposal_payload_hash, "proposal payload hash")
        _sha(self.config_hash, "proposal binding config hash")
        if not all((self.binding_id, self.plan_id, self.slot_id, self.proposal_id,
                    self.source_revision, self.code_version)):
            raise ValueError("proposal binding identity and provenance are required")
        if self.bound_at < self.proposed_at:
            raise ValueError("proposal binding cannot predate proposal")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("proposal binding disclosures must be canonical")

    @classmethod
    def create(cls, *, plan_id: str, slot_id: str, proposal_id: str,
               bound_at: datetime, proposed_at: datetime, proposal_payload_hash: str,
               source_revision: str, config: ArtifactTrustProposalPlanConfig
               ) -> ArtifactTrustProposalBinding:
        disclosures = tuple(sorted((
            "BINDING_IS_IMMUTABLE_AND_SINGLE_SLOT_SCOPED",
            "BOUND_PROPOSAL_REMAINS_UNAUTHENTICATED_AND_INACTIVE",
            "NO_CONSENSUS_READINESS_PROMOTION_OR_TRADING_AUTHORITY",
        )))
        fields = (plan_id, slot_id, proposal_id, bound_at, proposed_at, proposal_payload_hash,
                  source_revision, PACKAGE_VERSION, disclosures, config.config_hash)
        return cls(deterministic_id("artifact_trust_proposal_binding", fields), *fields)
