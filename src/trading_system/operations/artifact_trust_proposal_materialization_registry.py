"""Phase 6Y deterministic Phase 6X-to-6V catalog materialization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_policy_proposal_config import (
    ArtifactTrustPolicyProposalConfig,
)
from trading_system.operations.artifact_trust_policy_proposal_registry import (
    ArtifactTrustPolicyProposalRegistry,
)
from trading_system.operations.artifact_trust_proposal_catalog_config import (
    ArtifactTrustProposalCatalogConfig,
)
from trading_system.operations.artifact_trust_proposal_catalog_registry import (
    ArtifactTrustProposalCatalogRegistry,
)
from trading_system.operations.artifact_trust_proposal_materialization_config import (
    ArtifactTrustProposalMaterializationConfig,
)
from trading_system.operations.artifact_trust_proposal_materialization_contracts import (
    ArtifactTrustProposalMaterialization,
    ArtifactTrustProposalMaterializationStatus,
)
from trading_system.operations.artifact_trust_proposal_plan_config import (
    ArtifactTrustProposalPlanConfig,
)
from trading_system.operations.artifact_trust_proposal_plan_registry import (
    ArtifactTrustProposalPlanRegistry,
)
from trading_system.operations.artifact_trust_review_export_config import (
    ArtifactTrustReviewExportConfig,
)
from trading_system.operations.artifact_trust_review_export_registry import (
    ArtifactTrustReviewExportRegistry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proposal materialization time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid proposal materialization timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("proposal materialization time must be timezone-aware")
    return result


def _payload(text: str, digest: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("proposal materialization payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("proposal materialization payload is corrupt")
    return value


class ArtifactTrustProposalMaterializationRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ArtifactTrustProposalMaterializationConfig,
        plan_config: ArtifactTrustProposalPlanConfig,
        proposal_config: ArtifactTrustPolicyProposalConfig,
        review_config: ArtifactTrustReviewExportConfig,
        catalog_config: ArtifactTrustProposalCatalogConfig,
    ) -> None:
        self.repository = repository
        self.config = config
        reviews = ArtifactTrustReviewExportRegistry(repository, review_config)
        proposals = ArtifactTrustPolicyProposalRegistry(repository, proposal_config, reviews)
        self.plans = ArtifactTrustProposalPlanRegistry(
            repository, plan_config, proposals, reviews
        )
        self.catalogs = ArtifactTrustProposalCatalogRegistry(
            repository, catalog_config, proposals
        )

    def materialize(
        self,
        *,
        source_plan_id: str,
        materialized_at: datetime,
        cataloged_at: datetime,
        source_revision: str,
    ) -> ArtifactTrustProposalMaterialization:
        _time(materialized_at)
        _time(cataloged_at)
        if cataloged_at <= materialized_at:
            raise ValueError("catalog time must follow materialization")
        if not source_revision:
            raise ValueError("proposal materialization source revision is required")
        existing = self.repository.connection.execute(
            """SELECT materialized_at,cataloged_at,source_revision FROM
            operations_artifact_trust_proposal_materializations WHERE source_plan_id=?""",
            (source_plan_id,),
        ).fetchone()
        if existing is not None and existing != (
            _time(materialized_at),
            _time(cataloged_at),
            source_revision,
        ):
            raise ValueError("proposal plan is already materialized differently")
        status = self.plans.status(source_plan_id)
        if status["complete"] is not True:
            raise ValueError("prospective artifact trust proposal plan is incomplete")
        plan = status["plan"]
        raw_bindings = status["bindings"]
        if not isinstance(raw_bindings, list):
            raise ValueError("prospective artifact trust proposal bindings are corrupt")
        by_slot = {str(item["slot_id"]): item for item in raw_bindings}
        ordered = tuple(by_slot[slot.slot_id] for slot in plan.slots)
        latest_binding = max(_datetime(item["bound_at"]) for item in ordered)
        if materialized_at < latest_binding:
            raise ValueError("materialization cannot predate a proposal binding")
        proposal_ids = tuple(sorted(str(item["proposal_id"]) for item in ordered))
        catalog = self.catalogs.create(
            proposal_ids=proposal_ids,
            cataloged_at=cataloged_at,
            source_revision=source_revision,
        )
        self.catalogs.insert(catalog)
        plan_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_proposal_plans
            WHERE plan_id=?""",
            (source_plan_id,),
        ).fetchone()
        catalog_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_proposal_catalogs
            WHERE catalog_id=?""",
            (catalog.catalog_id,),
        ).fetchone()
        if plan_row is None or catalog_row is None:
            raise ValueError("proposal materialization source evidence is missing")
        binding_root = canonical_hash(tuple(
            (str(item["slot_id"]), str(item["proposal_id"]),
             str(item["proposal_payload_hash"]))
            for item in ordered
        ))
        return ArtifactTrustProposalMaterialization.create(
            source_plan_id=source_plan_id,
            catalog_id=catalog.catalog_id,
            materialized_at=materialized_at,
            cataloged_at=cataloged_at,
            proposal_ids=proposal_ids,
            slot_root_hash=plan.slot_root_hash,
            binding_root_hash=binding_root,
            plan_payload_hash=str(plan_row[0]),
            catalog_payload_hash=str(catalog_row[0]),
            slot_count=len(plan.slots),
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, item: ArtifactTrustProposalMaterialization) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("proposal materialization config hash mismatch")
        expected = self.materialize(
            source_plan_id=item.source_plan_id,
            materialized_at=item.materialized_at,
            cataloged_at=item.cataloged_at,
            source_revision=item.source_revision,
        )
        if item != expected:
            raise ValueError("proposal materialization source evidence is corrupt")
        text, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.materialization_id,
            item.source_plan_id,
            item.catalog_id,
            _time(item.materialized_at),
            _time(item.cataloged_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            text,
            digest,
        )
        with self.repository.connection:
            stored = self.repository.connection.execute(
                """SELECT materialization_id,source_plan_id,catalog_id,materialized_at,
                cataloged_at,status,source_revision,code_version,config_hash,payload_json,
                payload_hash FROM operations_artifact_trust_proposal_materializations
                WHERE materialization_id=?""",
                (item.materialization_id,),
            ).fetchone()
            if stored is not None:
                if stored != values:
                    raise ValueError("conflicting artifact trust proposal materialization")
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_artifact_trust_proposal_materializations
                WHERE source_plan_id=? OR catalog_id=?""",
                (item.source_plan_id, item.catalog_id),
            ).fetchone()
            if collision is not None:
                raise ValueError("proposal plan or catalog is already materialized")
            self.repository.connection.execute(
                """INSERT INTO operations_artifact_trust_proposal_materializations
                (materialization_id,source_plan_id,catalog_id,materialized_at,cataloged_at,status,
                 source_revision,code_version,config_hash,payload_json,payload_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
        return True

    def status(self, materialization_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM
            operations_artifact_trust_proposal_materializations WHERE materialization_id=?""",
            (materialization_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust proposal materialization")
        value = _payload(str(row[0]), str(row[1]))
        item = ArtifactTrustProposalMaterialization(
            str(value["materialization_id"]),
            str(value["source_plan_id"]),
            str(value["catalog_id"]),
            _datetime(value["materialized_at"]),
            _datetime(value["cataloged_at"]),
            tuple(str(proposal_id) for proposal_id in value["proposal_ids"]),
            str(value["slot_root_hash"]),
            str(value["binding_root_hash"]),
            str(value["plan_payload_hash"]),
            str(value["catalog_payload_hash"]),
            int(value["slot_count"]),
            ArtifactTrustProposalMaterializationStatus(str(value["status"])),
            bool(value["complete_population_claim"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(disclosure) for disclosure in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = ArtifactTrustProposalMaterialization.create(
            source_plan_id=item.source_plan_id,
            catalog_id=item.catalog_id,
            materialized_at=item.materialized_at,
            cataloged_at=item.cataloged_at,
            proposal_ids=item.proposal_ids,
            slot_root_hash=item.slot_root_hash,
            binding_root_hash=item.binding_root_hash,
            plan_payload_hash=item.plan_payload_hash,
            catalog_payload_hash=item.catalog_payload_hash,
            slot_count=item.slot_count,
            source_revision=item.source_revision,
            config=self.config,
        )
        if (
            item != expected
            or item.materialization_id != materialization_id
            or item.code_version != PACKAGE_VERSION
        ):
            raise ValueError("proposal materialization identity is corrupt")
        plan_status = self.plans.status(item.source_plan_id)
        if plan_status["complete"] is not True:
            raise ValueError("materialized proposal plan is incomplete")
        plan = plan_status["plan"]
        bindings = plan_status["bindings"]
        if not isinstance(bindings, list):
            raise ValueError("materialized proposal bindings are corrupt")
        by_slot = {str(binding["slot_id"]): binding for binding in bindings}
        ordered = tuple(by_slot[slot.slot_id] for slot in plan.slots)
        latest_binding = max(_datetime(binding["bound_at"]) for binding in ordered)
        proposal_ids = tuple(sorted(str(binding["proposal_id"]) for binding in ordered))
        binding_root = canonical_hash(tuple(
            (str(binding["slot_id"]), str(binding["proposal_id"]),
             str(binding["proposal_payload_hash"]))
            for binding in ordered
        ))
        catalog = self.catalogs.catalog(item.catalog_id)
        plan_row = self.repository.connection.execute(
            "SELECT payload_hash FROM operations_artifact_trust_proposal_plans WHERE plan_id=?",
            (item.source_plan_id,),
        ).fetchone()
        catalog_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_proposal_catalogs
            WHERE catalog_id=?""",
            (item.catalog_id,),
        ).fetchone()
        if (
            plan_row is None
            or catalog_row is None
            or item.proposal_ids != proposal_ids
            or item.slot_root_hash != plan.slot_root_hash
            or item.binding_root_hash != binding_root
            or item.plan_payload_hash != str(plan_row[0])
            or item.catalog_payload_hash != str(catalog_row[0])
            or item.slot_count != len(plan.slots)
            or catalog.proposal_ids != proposal_ids
            or catalog.cataloged_at != item.cataloged_at
            or catalog.source_revision != item.source_revision
            or item.materialized_at < latest_binding
        ):
            raise ValueError("proposal materialization source evidence is corrupt")
        return value
