"""Immutable Phase 6J plan-to-catalog materialization provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_catalog_config import (
    ProspectiveCatalogMaterializationConfig,
)
from trading_system.serialization import deterministic_id


@dataclass(frozen=True, slots=True)
class ProspectiveCatalogMaterialization:
    materialization_id: str
    plan_id: str
    catalog_id: str
    materialized_at: datetime
    slot_root_hash: str
    binding_root_hash: str
    catalog_root_hash: str
    slot_count: int
    source_revision: str
    code_version: str
    disclosures: tuple[str, ...]
    config_hash: str

    def __post_init__(self) -> None:
        if self.materialized_at.tzinfo is None or self.materialized_at.utcoffset() is None:
            raise ValueError("materialization timestamp must be timezone-aware")
        for value in (
            self.slot_root_hash,
            self.binding_root_hash,
            self.catalog_root_hash,
            self.config_hash,
        ):
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError("materialization hashes must be SHA-256 identities")
        if not all((self.materialization_id, self.plan_id, self.catalog_id, self.source_revision)):
            raise ValueError("materialization identity is required")
        if self.slot_count <= 0 or self.disclosures != tuple(sorted(set(self.disclosures))):
            raise ValueError("materialization evidence is invalid")

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        catalog_id: str,
        materialized_at: datetime,
        slot_root_hash: str,
        binding_root_hash: str,
        catalog_root_hash: str,
        slot_count: int,
        source_revision: str,
        config: ProspectiveCatalogMaterializationConfig,
    ) -> ProspectiveCatalogMaterialization:
        disclosures = tuple(
            sorted(
                (
                    "CATALOG_MEMBERSHIP_DERIVED_ONLY_FROM_FROZEN_SLOT_BINDINGS",
                    "MATERIALIZATION_DOES_NOT_AUTHENTICATE_REVIEWERS_OR_TIMESTAMPS",
                    "NO_CONSENSUS_OR_PRODUCTION_READINESS_INFERENCE",
                    "NO_PROMOTION_BROKER_OR_LIVE_TRADING_AUTHORITY",
                )
            )
        )
        identity = (
            plan_id,
            catalog_id,
            materialized_at,
            slot_root_hash,
            binding_root_hash,
            catalog_root_hash,
            slot_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
        return cls(
            deterministic_id("prospective_catalog_materialization", identity),
            plan_id,
            catalog_id,
            materialized_at,
            slot_root_hash,
            binding_root_hash,
            catalog_root_hash,
            slot_count,
            source_revision,
            PACKAGE_VERSION,
            disclosures,
            config.config_hash,
        )
