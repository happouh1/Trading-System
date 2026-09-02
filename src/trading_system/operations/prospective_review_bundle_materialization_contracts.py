"""Immutable Phase 6Q materialization evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_review_bundle_materialization_config import (
    ProspectiveReviewBundleMaterializationConfig,
)
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class ProspectiveReviewBundleMaterialization:
    materialization_id: str
    source_plan_id: str
    catalog_plan_id: str
    catalog_id: str
    materialized_at: datetime
    cataloged_at: datetime
    slot_root_hash: str
    binding_root_hash: str
    source_root_hash: str
    catalog_root_hash: str
    slot_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if any(
            value.tzinfo is None or value.utcoffset() is None
            for value in (self.materialized_at, self.cataloged_at)
        ):
            raise ValueError("materialization times must be timezone-aware")
        if self.cataloged_at <= self.materialized_at:
            raise ValueError("catalog time must follow materialization")
        for value in (
            self.slot_root_hash,
            self.binding_root_hash,
            self.source_root_hash,
            self.catalog_root_hash,
            self.config_hash,
        ):
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError("materialization hashes must be SHA-256 identities")
        if self.slot_count <= 0:
            raise ValueError("materialization requires slots")

    @classmethod
    def create(
        cls,
        *,
        source_plan_id: str,
        catalog_plan_id: str,
        catalog_id: str,
        materialized_at: datetime,
        cataloged_at: datetime,
        slot_root_hash: str,
        binding_root_hash: str,
        source_root_hash: str,
        catalog_root_hash: str,
        slot_count: int,
        source_revision: str,
        config: ProspectiveReviewBundleMaterializationConfig,
    ) -> ProspectiveReviewBundleMaterialization:
        disclosures = (
            "MEMBERSHIP_DERIVES_ONLY_FROM_PHASE6P_BINDINGS",
            "NO_CONSENSUS_READINESS_PROMOTION_OR_TRADING_AUTHORITY",
        )
        identity = (
            source_plan_id,
            catalog_plan_id,
            catalog_id,
            materialized_at,
            cataloged_at,
            slot_root_hash,
            binding_root_hash,
            source_root_hash,
            catalog_root_hash,
            slot_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_review_bundle_materialization", identity),
            source_plan_id,
            catalog_plan_id,
            catalog_id,
            materialized_at,
            cataloged_at,
            slot_root_hash,
            binding_root_hash,
            source_root_hash,
            catalog_root_hash,
            slot_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
