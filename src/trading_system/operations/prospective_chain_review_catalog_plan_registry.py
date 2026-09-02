"""Append-only Phase 6O catalog plans and exact later reconciliation."""

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
from trading_system.operations.prospective_chain_review_catalog_plan_contracts import (
    ProspectiveChainReviewCatalogPlan,
    ProspectiveChainReviewCatalogPlanReconciliation,
    ProspectiveChainReviewCatalogPlanSource,
)
from trading_system.operations.prospective_chain_review_catalog_registry import (
    ProspectiveChainReviewCatalogRegistry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("catalog plan time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid canonical catalog plan timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("catalog plan time must be timezone-aware")
    return result


def _root(payload: str, digest: str, name: str) -> dict[str, Any]:
    try:
        value: object = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != payload
        or canonical_hash(value) != digest
    ):
        raise ValueError(f"{name} payload is corrupt")
    return value


class ProspectiveChainReviewCatalogPlanRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ProspectiveChainReviewCatalogPlanConfig,
        catalog_config: ProspectiveChainReviewCatalogConfig,
    ) -> None:
        self.repository = repository
        self.config = config
        self.catalog_config = catalog_config

    def create_plan(
        self,
        *,
        catalog_name: str,
        registered_at: datetime,
        sources: tuple[tuple[str, str], ...],
        source_revision: str,
    ) -> ProspectiveChainReviewCatalogPlan:
        if not catalog_name or not source_revision or not sources:
            raise ValueError("prospective review catalog plan identity and sources are required")
        if len({bundle_id for bundle_id, _ in sources}) != len(sources):
            raise ValueError("planned prospective review bundle IDs must be unique")
        canonical = tuple(
            sorted(
                ProspectiveChainReviewCatalogPlanSource(bundle_id, verification_id)
                for bundle_id, verification_id in sources
            )
        )
        source_root = canonical_hash(
            tuple((item.bundle_id, item.verification_id) for item in canonical)
        )
        return ProspectiveChainReviewCatalogPlan.create(
            catalog_name=catalog_name,
            registered_at=registered_at,
            sources=canonical,
            source_root_hash=source_root,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ProspectiveChainReviewCatalogPlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("prospective review catalog plan config hash mismatch")
        text, digest = canonical_json(plan), canonical_hash(plan)
        values = (
            plan.plan_id,
            plan.catalog_name,
            _time(plan.registered_at),
            plan.source_root_hash,
            plan.source_revision,
            plan.code_version,
            plan.config_hash,
            text,
            digest,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_prospective_chain_review_catalog_plans
                   (plan_id,catalog_name,registered_at,source_root_hash,source_revision,
                    code_version,config_hash,payload_json,payload_hash)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT plan_id,catalog_name,registered_at,source_root_hash,source_revision,
                              code_version,config_hash,payload_json,payload_hash
                       FROM operations_prospective_chain_review_catalog_plans WHERE plan_id=?""",
                    (plan.plan_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError("conflicting prospective review catalog plan")
                return False
            for item in plan.sources:
                self.repository.connection.execute(
                    """INSERT INTO operations_prospective_chain_review_catalog_plan_sources
                       (plan_id,bundle_id,verification_id,payload_json,payload_hash)
                       VALUES (?,?,?,?,?)""",
                    (
                        plan.plan_id,
                        item.bundle_id,
                        item.verification_id,
                        canonical_json(item),
                        canonical_hash(item),
                    ),
                )
        return True

    def plan(self, plan_id: str) -> ProspectiveChainReviewCatalogPlan:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
               FROM operations_prospective_chain_review_catalog_plans WHERE plan_id=?""",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective review catalog plan")
        value = _root(str(row[0]), str(row[1]), "prospective review catalog plan")
        raw_sources = value.get("sources")
        if not isinstance(raw_sources, list) or not all(
            isinstance(item, dict) for item in raw_sources
        ):
            raise ValueError("prospective review catalog plan sources are corrupt")
        sources = tuple(
            ProspectiveChainReviewCatalogPlanSource(
                str(item["bundle_id"]), str(item["verification_id"])
            )
            for item in raw_sources
        )
        plan = ProspectiveChainReviewCatalogPlan(
            str(value["plan_id"]),
            str(value["catalog_name"]),
            _datetime(value["registered_at"]),
            sources,
            str(value["source_root_hash"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected_root = canonical_hash(
            tuple((item.bundle_id, item.verification_id) for item in plan.sources)
        )
        if (
            plan.config_hash != self.config.config_hash
            or plan.code_version != PACKAGE_VERSION
            or plan.source_root_hash != expected_root
        ):
            raise ValueError("prospective review catalog plan provenance mismatch")
        rows = self.repository.connection.execute(
            """SELECT bundle_id,verification_id,payload_json,payload_hash
               FROM operations_prospective_chain_review_catalog_plan_sources
               WHERE plan_id=? ORDER BY bundle_id""",
            (plan_id,),
        ).fetchall()
        if len(rows) != len(plan.sources):
            raise ValueError("prospective review catalog plan sources are incomplete")
        for stored, item in zip(rows, plan.sources, strict=True):
            if (
                (str(stored[0]), str(stored[1]))
                != (item.bundle_id, item.verification_id)
                or canonical_json(item) != str(stored[2])
                or canonical_hash(item) != str(stored[3])
            ):
                raise ValueError("prospective review catalog plan source is corrupt")
        return plan

    def reconcile(
        self,
        *,
        plan_id: str,
        catalog_id: str,
        reconciled_at: datetime,
        source_revision: str,
    ) -> ProspectiveChainReviewCatalogPlanReconciliation:
        plan = self.plan(plan_id)
        if reconciled_at < plan.registered_at:
            raise ValueError("catalog reconciliation cannot predate plan registration")
        plan_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_prospective_chain_review_catalog_plans
               WHERE plan_id=?""",
            (plan_id,),
        ).fetchone()
        assert plan_row is not None
        catalog_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_prospective_chain_review_catalogs
               WHERE catalog_id=?""",
            (catalog_id,),
        ).fetchone()
        missing, corrupt = catalog_row is None, False
        reasons: list[str] = []
        actual_count = 0
        catalog_hash: str | None = None
        if missing:
            reasons.append("CATALOG_MISSING")
        else:
            try:
                catalog = ProspectiveChainReviewCatalogRegistry(
                    self.repository, self.catalog_config
                ).status(catalog_id)
                catalog_hash = str(catalog_row[0])
                if reconciled_at < catalog.cataloged_at:
                    raise ValueError("catalog reconciliation cannot predate catalog")
                if catalog.cataloged_at <= plan.registered_at:
                    reasons.append("CATALOG_NOT_AFTER_PLAN")
                    corrupt = True
                if catalog.catalog_name != plan.catalog_name:
                    reasons.append("CATALOG_NAME_MISMATCH")
                expected = {item.bundle_id: item.verification_id for item in plan.sources}
                actual = {item.bundle_id: item.verification_id for item in catalog.entries}
                actual_count = len(actual)
                if expected.keys() - actual.keys():
                    reasons.append("PLANNED_BUNDLE_MISSING")
                if actual.keys() - expected.keys():
                    reasons.append("UNPLANNED_BUNDLE_PRESENT")
                if any(
                    actual.get(bundle_id) != verification_id
                    for bundle_id, verification_id in expected.items()
                    if bundle_id in actual
                ):
                    reasons.append("BUNDLE_VERIFICATION_CHANGED")
            except ValueError:
                reasons.append("CATALOG_PAYLOAD_CORRUPT")
                corrupt, catalog_hash = True, None
        return ProspectiveChainReviewCatalogPlanReconciliation.create(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=reconciled_at,
            reasons=tuple(reasons),
            missing=missing,
            corrupt=corrupt,
            plan_payload_hash=str(plan_row[0]),
            catalog_payload_hash=catalog_hash,
            expected_bundle_count=len(plan.sources),
            actual_bundle_count=actual_count,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_reconciliation(
        self, result: ProspectiveChainReviewCatalogPlanReconciliation
    ) -> bool:
        if result.config_hash != self.config.config_hash:
            raise ValueError("catalog reconciliation config hash mismatch")
        text, digest = canonical_json(result), canonical_hash(result)
        values = (
            result.reconciliation_id,
            result.plan_id,
            result.catalog_id,
            _time(result.reconciled_at),
            result.status.value,
            result.source_revision,
            result.code_version,
            result.config_hash,
            text,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_prospective_chain_review_catalog_reconciliations
               (reconciliation_id,plan_id,catalog_id,reconciled_at,status,source_revision,
                code_version,config_hash,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT reconciliation_id,plan_id,catalog_id,reconciled_at,status,
                          source_revision,code_version,config_hash,payload_json,payload_hash
                   FROM operations_prospective_chain_review_catalog_reconciliations
                   WHERE reconciliation_id=?""",
                (result.reconciliation_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting prospective review catalog reconciliation")
            return False
        self.repository.connection.commit()
        return True

    def reconciliation(self, reconciliation_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
               FROM operations_prospective_chain_review_catalog_reconciliations
               WHERE reconciliation_id=?""",
            (reconciliation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective review catalog reconciliation")
        return _root(str(row[0]), str(row[1]), "prospective review catalog reconciliation")
