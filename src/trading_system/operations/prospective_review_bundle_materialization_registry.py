"""Phase 6Q deterministic Phase 6P-to-6O/6N materialization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_catalog_config import (
    ProspectiveChainReviewCatalogConfig,
)
from trading_system.operations.prospective_chain_review_catalog_plan_config import (
    ProspectiveChainReviewCatalogPlanConfig,
)
from trading_system.operations.prospective_chain_review_catalog_plan_registry import (
    ProspectiveChainReviewCatalogPlanRegistry,
)
from trading_system.operations.prospective_chain_review_catalog_registry import (
    ProspectiveChainReviewCatalogRegistry,
)
from trading_system.operations.prospective_review_bundle_materialization_config import (
    ProspectiveReviewBundleMaterializationConfig,
)
from trading_system.operations.prospective_review_bundle_materialization_contracts import (
    ProspectiveReviewBundleMaterialization,
)
from trading_system.operations.prospective_review_bundle_plan_config import (
    ProspectiveReviewBundlePlanConfig,
)
from trading_system.operations.prospective_review_bundle_plan_registry import (
    ProspectiveReviewBundlePlanRegistry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("materialization time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _root(text: str, digest: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("review-bundle materialization payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("review-bundle materialization payload is corrupt")
    return value


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid review-bundle materialization timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("materialization time must be timezone-aware")
    return result


class ProspectiveReviewBundleMaterializationRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ProspectiveReviewBundleMaterializationConfig,
        plan_config: ProspectiveReviewBundlePlanConfig,
        catalog_plan_config: ProspectiveChainReviewCatalogPlanConfig,
        catalog_config: ProspectiveChainReviewCatalogConfig,
    ) -> None:
        self.repository = repository
        self.config = config
        self.plans = ProspectiveReviewBundlePlanRegistry(repository, plan_config, catalog_config)
        self.catalog_plans = ProspectiveChainReviewCatalogPlanRegistry(
            repository, catalog_plan_config, catalog_config
        )
        self.catalogs = ProspectiveChainReviewCatalogRegistry(repository, catalog_config)

    def materialize(
        self,
        *,
        source_plan_id: str,
        materialized_at: datetime,
        cataloged_at: datetime,
        source_revision: str,
    ) -> ProspectiveReviewBundleMaterialization:
        _time(materialized_at)
        _time(cataloged_at)
        if cataloged_at <= materialized_at:
            raise ValueError("catalog time must follow materialization")
        if not source_revision:
            raise ValueError("materialization source revision is required")
        existing = self.repository.connection.execute(
            """SELECT materialized_at,cataloged_at,source_revision
            FROM operations_prospective_review_bundle_materializations
            WHERE source_plan_id=?""",
            (source_plan_id,),
        ).fetchone()
        if existing is not None and existing != (
            _time(materialized_at),
            _time(cataloged_at),
            source_revision,
        ):
            raise ValueError("review-bundle plan is already materialized differently")
        status = self.plans.status(source_plan_id)
        if status["complete"] is not True:
            raise ValueError("prospective review-bundle plan is incomplete")
        plan = status["plan"]
        raw_bindings = status["bindings"]
        if not isinstance(raw_bindings, list):
            raise ValueError("prospective review-bundle bindings are corrupt")
        by_slot = {str(item["slot_id"]): item for item in raw_bindings}
        ordered = tuple(by_slot[slot.slot_id] for slot in plan.slots)
        if materialized_at < max(
            datetime.fromisoformat(str(item["bound_at"]["__datetime__"]).replace("Z", "+00:00"))
            for item in ordered
        ):
            raise ValueError("materialization cannot predate a binding")
        sources = tuple((str(item["bundle_id"]), str(item["verification_id"])) for item in ordered)
        catalog_plan = self.catalog_plans.create_plan(
            catalog_name=plan.catalog_name,
            registered_at=materialized_at,
            sources=sources,
            source_revision=source_revision,
        )
        self.catalog_plans.insert_plan(catalog_plan)
        catalog = self.catalogs.create(
            catalog_name=plan.catalog_name,
            cataloged_at=cataloged_at,
            sources=sources,
            source_revision=source_revision,
        )
        self.catalogs.insert(catalog)
        binding_root = canonical_hash(
            tuple(
                (str(item["slot_id"]), str(item["bundle_id"]), str(item["verification_id"]))
                for item in ordered
            )
        )
        return ProspectiveReviewBundleMaterialization.create(
            source_plan_id=source_plan_id,
            catalog_plan_id=catalog_plan.plan_id,
            catalog_id=catalog.catalog_id,
            materialized_at=materialized_at,
            cataloged_at=cataloged_at,
            slot_root_hash=plan.slot_root_hash,
            binding_root_hash=binding_root,
            source_root_hash=catalog_plan.source_root_hash,
            catalog_root_hash=catalog.catalog_root_hash,
            slot_count=len(plan.slots),
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, item: ProspectiveReviewBundleMaterialization) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("materialization config hash mismatch")
        text, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.materialization_id,
            item.source_plan_id,
            item.catalog_plan_id,
            item.catalog_id,
            _time(item.materialized_at),
            _time(item.cataloged_at),
            item.source_revision,
            item.code_version,
            item.config_hash,
            text,
            digest,
        )
        with self.repository.connection:
            stored = self.repository.connection.execute(
                """SELECT materialization_id,source_plan_id,catalog_plan_id,catalog_id,
                materialized_at,cataloged_at,source_revision,code_version,config_hash,payload_json,
                payload_hash FROM operations_prospective_review_bundle_materializations
                WHERE materialization_id=?""",
                (item.materialization_id,),
            ).fetchone()
            if stored is not None:
                if stored != values:
                    raise ValueError("conflicting review-bundle materialization")
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_prospective_review_bundle_materializations
                WHERE source_plan_id=? OR catalog_plan_id=? OR catalog_id=?""",
                (item.source_plan_id, item.catalog_plan_id, item.catalog_id),
            ).fetchone()
            if collision is not None:
                raise ValueError("review-bundle plan or catalog is already materialized")
            self.repository.connection.execute(
                """INSERT INTO operations_prospective_review_bundle_materializations
                (materialization_id,source_plan_id,catalog_plan_id,catalog_id,materialized_at,
                cataloged_at,source_revision,code_version,config_hash,payload_json,payload_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
        return True

    def status(self, materialization_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
            FROM operations_prospective_review_bundle_materializations
            WHERE materialization_id=?""",
            (materialization_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown review-bundle materialization")
        value = _root(str(row[0]), str(row[1]))
        if (
            value.get("materialization_id") != materialization_id
            or value.get("code_version") != PACKAGE_VERSION
            or value.get("config_hash") != self.config.config_hash
        ):
            raise ValueError("review-bundle materialization provenance is corrupt")
        item = ProspectiveReviewBundleMaterialization(
            str(value["materialization_id"]),
            str(value["source_plan_id"]),
            str(value["catalog_plan_id"]),
            str(value["catalog_id"]),
            _datetime(value["materialized_at"]),
            _datetime(value["cataloged_at"]),
            str(value["slot_root_hash"]),
            str(value["binding_root_hash"]),
            str(value["source_root_hash"]),
            str(value["catalog_root_hash"]),
            int(value["slot_count"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(disclosure) for disclosure in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = ProspectiveReviewBundleMaterialization.create(
            source_plan_id=item.source_plan_id,
            catalog_plan_id=item.catalog_plan_id,
            catalog_id=item.catalog_id,
            materialized_at=item.materialized_at,
            cataloged_at=item.cataloged_at,
            slot_root_hash=item.slot_root_hash,
            binding_root_hash=item.binding_root_hash,
            source_root_hash=item.source_root_hash,
            catalog_root_hash=item.catalog_root_hash,
            slot_count=item.slot_count,
            source_revision=item.source_revision,
            config=self.config,
        )
        if item != expected:
            raise ValueError("review-bundle materialization identity is corrupt")
        plan_status = self.plans.status(str(value["source_plan_id"]))
        if plan_status["complete"] is not True:
            raise ValueError("materialized review-bundle plan is incomplete")
        catalog_plan = self.catalog_plans.plan(str(value["catalog_plan_id"]))
        catalog = self.catalogs.status(str(value["catalog_id"]))
        plan = plan_status["plan"]
        bindings = plan_status["bindings"]
        if not isinstance(bindings, list):
            raise ValueError("materialized review-bundle bindings are corrupt")
        by_slot = {str(item["slot_id"]): item for item in bindings}
        ordered = tuple(by_slot[slot.slot_id] for slot in plan.slots)
        sources = tuple((str(item["bundle_id"]), str(item["verification_id"])) for item in ordered)
        binding_root = canonical_hash(
            tuple(
                (str(item["slot_id"]), *source)
                for item, source in zip(ordered, sources, strict=True)
            )
        )
        if (
            value.get("slot_root_hash") != plan.slot_root_hash
            or value.get("binding_root_hash") != binding_root
            or value.get("source_root_hash") != catalog_plan.source_root_hash
            or value.get("catalog_root_hash") != catalog.catalog_root_hash
            or value.get("slot_count") != len(plan.slots)
            or catalog_plan.catalog_name != plan.catalog_name
            or catalog.catalog_name != plan.catalog_name
            or catalog_plan.registered_at != item.materialized_at
            or catalog.cataloged_at != item.cataloged_at
            or catalog_plan.source_revision != item.source_revision
            or catalog.source_revision != item.source_revision
            or tuple((item.bundle_id, item.verification_id) for item in catalog_plan.sources)
            != tuple(sorted(sources))
            or {(item.bundle_id, item.verification_id) for item in catalog.entries} != set(sources)
        ):
            raise ValueError("review-bundle materialization source evidence is corrupt")
        return value
