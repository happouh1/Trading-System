"""Immutable Phase 6P prospective review-bundle slots and bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_review_bundle_plan_config import (
    ProspectiveReviewBundlePlanConfig,
)
from trading_system.serialization import deterministic_id


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("prospective review-bundle time must be timezone-aware")


def _sha(value: str, name: str) -> None:
    if not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a SHA-256 identity")


@dataclass(frozen=True, slots=True, order=True)
class ProspectiveReviewBundleSlot:
    slot_id: str
    expected_as_of: datetime

    def __post_init__(self) -> None:
        _aware(self.expected_as_of)
        if not self.slot_id:
            raise ValueError("review-bundle slot ID is required")


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundlePlan:
    plan_id: str
    catalog_name: str
    registered_at: datetime
    slots: tuple[ProspectiveReviewBundleSlot, ...]
    slot_root_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.registered_at)
        _sha(self.slot_root_hash, "review-bundle slot root")
        _sha(self.config_hash, "review-bundle plan config hash")
        if not all((self.plan_id, self.catalog_name, self.source_revision, self.code_version)):
            raise ValueError("review-bundle plan identity is required")
        if not self.slots or self.registered_at >= min(item.expected_as_of for item in self.slots):
            raise ValueError("plan registration must precede every expected slot")
        if self.slots != tuple(sorted(set(self.slots))):
            raise ValueError("review-bundle slots must be unique and canonical")
        if len({item.slot_id for item in self.slots}) != len(self.slots) or len(
            {item.expected_as_of for item in self.slots}
        ) != len(self.slots):
            raise ValueError("review-bundle slot IDs and expected times must be unique")

    @classmethod
    def create(
        cls,
        *,
        catalog_name: str,
        registered_at: datetime,
        slots: tuple[ProspectiveReviewBundleSlot, ...],
        slot_root_hash: str,
        source_revision: str,
        config: ProspectiveReviewBundlePlanConfig,
    ) -> ProspectiveReviewBundlePlan:
        disclosures = tuple(
            sorted(
                (
                    "CONTENT_DERIVED_BUNDLE_IDS_ARE_UNKNOWN_AT_REGISTRATION",
                    "EXPECTED_TIMES_ARE_DESCRIPTIVE_WITH_NO_TOLERANCE_POLICY",
                    "NO_CONSENSUS_READINESS_PROMOTION_OR_TRADING_AUTHORITY",
                    "REVIEWER_IDENTITIES_REMAIN_UNAUTHENTICATED",
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
            deterministic_id("prospective_review_bundle_plan", identity),
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
class ProspectiveReviewBundleBinding:
    binding_id: str
    plan_id: str
    slot_id: str
    bundle_id: str
    verification_id: str
    bound_at: datetime
    bundle_verified_at: datetime
    artifact_hash: str
    chain_root_hash: str
    review_root_hash: str
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        _aware(self.bound_at)
        _aware(self.bundle_verified_at)
        for value, name in (
            (self.artifact_hash, "artifact hash"),
            (self.chain_root_hash, "chain root"),
            (self.review_root_hash, "review root"),
            (self.config_hash, "binding config hash"),
        ):
            _sha(value, name)
        if self.bound_at < self.bundle_verified_at:
            raise ValueError("binding cannot predate bundle verification")
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
            raise ValueError("review-bundle binding identity is required")

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
        artifact_hash: str,
        chain_root_hash: str,
        review_root_hash: str,
        source_revision: str,
        config: ProspectiveReviewBundlePlanConfig,
    ) -> ProspectiveReviewBundleBinding:
        disclosures = (
            "BINDING_IS_IMMUTABLE_AND_SINGLE_SLOT_SCOPED",
            "NO_CONSENSUS_OR_TRADING_AUTHORITY",
        )
        identity = (
            plan_id,
            slot_id,
            bundle_id,
            verification_id,
            bound_at,
            bundle_verified_at,
            artifact_hash,
            chain_root_hash,
            review_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_review_bundle_binding", identity),
            plan_id,
            slot_id,
            bundle_id,
            verification_id,
            bound_at,
            bundle_verified_at,
            artifact_hash,
            chain_root_hash,
            review_root_hash,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
