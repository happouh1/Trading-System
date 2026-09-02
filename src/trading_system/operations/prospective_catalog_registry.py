"""Phase 6J deterministic materialization of prospective plans into catalogs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_review_catalog_config import (
    ObservationAuditReviewCatalogConfig,
)
from trading_system.operations.audit_review_catalog_registry import (
    ObservationAuditReviewCatalogRegistry,
)
from trading_system.operations.prospective_catalog_config import (
    ProspectiveCatalogMaterializationConfig,
)
from trading_system.operations.prospective_catalog_contracts import (
    ProspectiveCatalogMaterialization,
)
from trading_system.operations.prospective_review_config import ProspectiveReviewPlanConfig
from trading_system.operations.prospective_review_contracts import ProspectiveReviewBinding
from trading_system.operations.prospective_review_registry import ProspectiveReviewPlanRegistry
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("materialization timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _root(payload_json: str, payload_hash: str) -> dict[str, Any]:
    try:
        value: object = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise ValueError("materialization payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != payload_json
        or canonical_hash(value) != payload_hash
    ):
        raise ValueError("materialization payload is corrupt")
    return value


class ProspectiveCatalogMaterializationRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ProspectiveCatalogMaterializationConfig,
        prospective_config: ProspectiveReviewPlanConfig,
        catalog_config: ObservationAuditReviewCatalogConfig,
    ) -> None:
        self.repository = repository
        self.config = config
        self.prospective = ProspectiveReviewPlanRegistry(repository, prospective_config)
        self.catalogs = ObservationAuditReviewCatalogRegistry(repository, catalog_config)

    def materialize(
        self, *, plan_id: str, materialized_at: datetime, source_revision: str
    ) -> ProspectiveCatalogMaterialization:
        status = self.prospective.status(plan_id)
        if status["complete"] is not True:
            raise ValueError("prospective review plan is incomplete")
        plan = status["plan"]
        bindings = tuple(status["bindings"])
        if not all(isinstance(item, ProspectiveReviewBinding) for item in bindings):
            raise ValueError("prospective review bindings are corrupt")
        by_slot = {binding.slot_id: binding for binding in bindings}
        ordered = tuple(by_slot[slot.slot_id] for slot in plan.slots)
        binding_root = canonical_hash(
            tuple(
                (binding.slot_id, binding.bundle_id, binding.verification_id) for binding in ordered
            )
        )
        catalog = self.catalogs.create(
            catalog_name=plan.catalog_name,
            cataloged_at=materialized_at,
            sources=tuple((binding.bundle_id, binding.verification_id) for binding in ordered),
            source_revision=source_revision,
        )
        self.catalogs.insert(catalog)
        return ProspectiveCatalogMaterialization.create(
            plan_id=plan.plan_id,
            catalog_id=catalog.catalog_id,
            materialized_at=materialized_at,
            slot_root_hash=plan.slot_root_hash,
            binding_root_hash=binding_root,
            catalog_root_hash=catalog.catalog_root_hash,
            slot_count=len(plan.slots),
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, evidence: ProspectiveCatalogMaterialization) -> bool:
        payload_json, payload_hash = canonical_json(evidence), canonical_hash(evidence)
        values = (
            evidence.materialization_id,
            evidence.plan_id,
            evidence.catalog_id,
            _time(evidence.materialized_at),
            evidence.source_revision,
            evidence.code_version,
            evidence.config_hash,
            payload_json,
            payload_hash,
        )
        with self.repository.connection:
            stored = self.repository.connection.execute(
                """SELECT materialization_id, plan_id, catalog_id, materialized_at,
                          source_revision, code_version, config_hash, payload_json, payload_hash
                   FROM operations_prospective_catalog_materializations
                   WHERE materialization_id = ?""",
                (evidence.materialization_id,),
            ).fetchone()
            if stored is not None:
                if stored != values:
                    raise ValueError("conflicting prospective catalog materialization")
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_prospective_catalog_materializations
                   WHERE plan_id=? OR catalog_id=?""",
                (evidence.plan_id, evidence.catalog_id),
            ).fetchone()
            if collision is not None:
                raise ValueError("prospective plan or catalog is already materialized")
            self.repository.connection.execute(
                """INSERT INTO operations_prospective_catalog_materializations
                   (materialization_id,plan_id,catalog_id,materialized_at,source_revision,code_version,
                    config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)""",
                values,
            )
        return True

    def status(self, materialization_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_prospective_catalog_materializations
               WHERE materialization_id=?""",
            (materialization_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective catalog materialization")
        value = _root(str(row[0]), str(row[1]))
        if (
            value.get("materialization_id") != materialization_id
            or value.get("code_version") != PACKAGE_VERSION
            or value.get("config_hash") != self.config.config_hash
        ):
            raise ValueError("materialization provenance is corrupt")
        plan_status = self.prospective.status(str(value["plan_id"]))
        if plan_status["complete"] is not True:
            raise ValueError("materialized prospective plan is no longer complete")
        catalog = self.catalogs.status(str(value["catalog_id"]))
        plan = plan_status["plan"]
        bindings = tuple(plan_status["bindings"])
        binding_root = canonical_hash(
            tuple(
                (binding.slot_id, binding.bundle_id, binding.verification_id)
                for binding in sorted(bindings, key=lambda item: item.slot_id)
            )
        )
        if (
            value.get("slot_root_hash") != plan.slot_root_hash
            or value.get("binding_root_hash") != binding_root
            or value.get("catalog_root_hash") != catalog.catalog_root_hash
            or value.get("slot_count") != len(plan.slots)
            or catalog.catalog_name != plan.catalog_name
            or {(entry.bundle_id, entry.verification_id) for entry in catalog.entries}
            != {(binding.bundle_id, binding.verification_id) for binding in bindings}
        ):
            raise ValueError("materialization source evidence is corrupt")
        return value
