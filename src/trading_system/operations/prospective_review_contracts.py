"""Immutable Phase 6I prospective review-slot evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_review_config import ProspectiveReviewPlanConfig
from trading_system.serialization import deterministic_id


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("prospective review timestamp must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


@dataclass(frozen=True, slots=True, order=True)
class ProspectiveReviewSlot:
    slot_id: str
    expected_as_of: datetime

    def __post_init__(self) -> None:
        _aware(self.expected_as_of)
        if not self.slot_id:
            raise ValueError("prospective review slot ID is required")


@dataclass(frozen=True, slots=True)
class ProspectiveReviewPlan:
    plan_id: str
    catalog_name: str
    registered_at: datetime
    slots: tuple[ProspectiveReviewSlot, ...]
    slot_root_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.registered_at)
        _sha(self.slot_root_hash, "prospective review slot root")
        _sha(self.config_hash, "prospective review configuration hash")
        if not all((self.plan_id, self.catalog_name, self.source_revision, self.code_version)):
            raise ValueError("prospective review plan identity is required")
        if not self.slots or self.registered_at >= min(slot.expected_as_of for slot in self.slots):
            raise ValueError("plan registration must precede every expected slot")
        if self.slots != tuple(sorted(set(self.slots))):
            raise ValueError("prospective review slots must be unique and canonical")
        if len({slot.slot_id for slot in self.slots}) != len(self.slots) or len(
            {slot.expected_as_of for slot in self.slots}
        ) != len(self.slots):
            raise ValueError("slot IDs and expected times must be unique")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("prospective review plan disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        catalog_name: str,
        registered_at: datetime,
        slots: tuple[ProspectiveReviewSlot, ...],
        slot_root_hash: str,
        source_revision: str,
        config: ProspectiveReviewPlanConfig,
    ) -> ProspectiveReviewPlan:
        disclosures = tuple(
            sorted(
                (
                    "MATCHED_SLOT_BINDINGS_DO_NOT_PROVE_REVIEWER_INDEPENDENCE",
                    "NO_AUTOMATIC_PROMOTION_AUTHORITY",
                    "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
                    "NO_CONSENSUS_OR_PRODUCTION_READINESS_INFERENCE",
                    "SLOTS_ARE_REGISTERED_BEFORE_CONTENT_IDENTITIES_EXIST",
                )
            )
        )
        identity = (
            catalog_name,
            registered_at,
            slots,
            slot_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_review_plan", identity),
            catalog_name,
            registered_at,
            slots,
            slot_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBinding:
    binding_id: str
    plan_id: str
    slot_id: str
    bundle_id: str
    verification_id: str
    bound_at: datetime
    bundle_verified_at: datetime
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.bound_at)
        _aware(self.bundle_verified_at)
        _sha(self.config_hash, "prospective review binding configuration hash")
        if not all(
            (
                self.binding_id,
                self.plan_id,
                self.slot_id,
                self.bundle_id,
                self.verification_id,
                self.source_revision,
                self.code_version,
            )
        ):
            raise ValueError("prospective review binding identity is required")
        if self.bound_at < self.bundle_verified_at:
            raise ValueError("binding cannot predate bundle verification")
        if self.disclosures != tuple(sorted(set(self.disclosures))) or not self.disclosures:
            raise ValueError("prospective review binding disclosures must be canonical")

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        slot_id: str,
        bundle_id: str,
        verification_id: str,
        bound_at: datetime,
        bundle_verified_at: datetime,
        source_revision: str,
        config: ProspectiveReviewPlanConfig,
    ) -> ProspectiveReviewBinding:
        disclosures = tuple(
            sorted(
                (
                    "BINDING_IS_IMMUTABLE_AND_SINGLE_SLOT_SCOPED",
                    "NO_CONSENSUS_OR_TRADING_AUTHORITY",
                    "REVIEWER_IDENTITIES_REMAIN_UNAUTHENTICATED",
                )
            )
        )
        identity = (
            plan_id,
            slot_id,
            bundle_id,
            verification_id,
            bound_at,
            bundle_verified_at,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_review_binding", identity),
            plan_id,
            slot_id,
            bundle_id,
            verification_id,
            bound_at,
            bundle_verified_at,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
