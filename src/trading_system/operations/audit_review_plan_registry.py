"""Append-only Phase 6H review-catalog plans and exact reconciliation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_review_catalog_contracts import (
    ReviewBundleCatalog,
    ReviewBundleCatalogEntry,
)
from trading_system.operations.audit_review_plan_config import ReviewCatalogPlanConfig
from trading_system.operations.audit_review_plan_contracts import (
    ReviewCatalogPlan,
    ReviewCatalogPlanReconciliation,
    ReviewCatalogPlanSource,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review catalog plan timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid canonical review catalog plan timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("review catalog plan timestamp must be timezone-aware")
    return result


def _root(payload_json: str, payload_hash: str, name: str) -> dict[str, Any]:
    try:
        value: object = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != payload_json
        or canonical_hash(value) != payload_hash
    ):
        raise ValueError(f"{name} payload is corrupt")
    return value


class ReviewCatalogPlanRegistry:
    def __init__(self, repository: SQLiteRepository, config: ReviewCatalogPlanConfig) -> None:
        self.repository = repository
        self.config = config

    def create_plan(
        self,
        *,
        catalog_name: str,
        registered_at: datetime,
        sources: tuple[tuple[str, str], ...],
        source_revision: str,
    ) -> ReviewCatalogPlan:
        if not catalog_name or not source_revision or not sources:
            raise ValueError("review catalog plan identity and sources are required")
        if len({bundle_id for bundle_id, _ in sources}) != len(sources):
            raise ValueError("planned bundle IDs must be unique")
        canonical_sources = tuple(
            sorted(
                ReviewCatalogPlanSource(bundle_id, verification_id)
                for bundle_id, verification_id in sources
            )
        )
        root_hash = canonical_hash(
            tuple((source.bundle_id, source.verification_id) for source in canonical_sources)
        )
        return ReviewCatalogPlan.create(
            catalog_name=catalog_name,
            registered_at=registered_at,
            sources=canonical_sources,
            source_root_hash=root_hash,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ReviewCatalogPlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("review catalog plan configuration hash mismatch")
        payload_json = canonical_json(plan)
        payload_hash = canonical_hash(plan)
        values = (
            plan.plan_id,
            plan.catalog_name,
            _time(plan.registered_at),
            plan.source_root_hash,
            plan.source_revision,
            plan.code_version,
            plan.config_hash,
            payload_json,
            payload_hash,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_review_catalog_plans
                   (plan_id, catalog_name, registered_at, source_root_hash, source_revision,
                    code_version, config_hash, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT plan_id, catalog_name, registered_at, source_root_hash,
                              source_revision, code_version, config_hash, payload_json, payload_hash
                       FROM operations_review_catalog_plans WHERE plan_id = ?""",
                    (plan.plan_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(f"conflicting review catalog plan: {plan.plan_id}")
                return False
            for source in plan.sources:
                self.repository.connection.execute(
                    """INSERT INTO operations_review_catalog_plan_sources
                       (plan_id, bundle_id, verification_id, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        plan.plan_id,
                        source.bundle_id,
                        source.verification_id,
                        canonical_json(source),
                        canonical_hash(source),
                    ),
                )
        return True

    def plan(self, plan_id: str) -> ReviewCatalogPlan:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash
               FROM operations_review_catalog_plans WHERE plan_id = ?""",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown review catalog plan")
        value = _root(str(row[0]), str(row[1]), "review catalog plan")
        raw_sources = value.get("sources")
        if not isinstance(raw_sources, list) or not all(
            isinstance(source, dict) for source in raw_sources
        ):
            raise ValueError("review catalog plan sources are corrupt")
        sources = tuple(
            ReviewCatalogPlanSource(str(source["bundle_id"]), str(source["verification_id"]))
            for source in raw_sources
        )
        plan = ReviewCatalogPlan(
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
            tuple((source.bundle_id, source.verification_id) for source in plan.sources)
        )
        if (
            plan.config_hash != self.config.config_hash
            or plan.code_version != PACKAGE_VERSION
            or plan.source_root_hash != expected_root
        ):
            raise ValueError("review catalog plan provenance mismatch")
        rows = self.repository.connection.execute(
            """SELECT bundle_id, verification_id, payload_json, payload_hash
               FROM operations_review_catalog_plan_sources WHERE plan_id = ? ORDER BY bundle_id""",
            (plan_id,),
        ).fetchall()
        if len(rows) != len(plan.sources):
            raise ValueError("review catalog plan child sources are incomplete")
        for row_value, source in zip(rows, plan.sources, strict=True):
            if (
                (str(row_value[0]), str(row_value[1]))
                != (source.bundle_id, source.verification_id)
                or canonical_json(source) != str(row_value[2])
                or canonical_hash(source) != str(row_value[3])
            ):
                raise ValueError("review catalog plan child source is corrupt")
        return plan

    def reconcile(
        self,
        *,
        plan_id: str,
        catalog_id: str,
        reconciled_at: datetime,
        source_revision: str,
    ) -> ReviewCatalogPlanReconciliation:
        plan = self.plan(plan_id)
        if reconciled_at < plan.registered_at:
            raise ValueError("reconciliation cannot predate plan registration")
        plan_row = self.repository.connection.execute(
            "SELECT payload_hash FROM operations_review_catalog_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        assert plan_row is not None
        catalog_row = self.repository.connection.execute(
            """SELECT catalog_name, cataloged_at, code_version, payload_json, payload_hash
               FROM operations_observation_audit_review_catalogs WHERE catalog_id = ?""",
            (catalog_id,),
        ).fetchone()
        reasons: list[str] = []
        missing = catalog_row is None
        corrupt = False
        actual_count = 0
        catalog_hash: str | None = None
        if missing:
            reasons.append("CATALOG_MISSING")
        else:
            try:
                catalog = _root(str(catalog_row[3]), str(catalog_row[4]), "review catalog")
                catalog_hash = str(catalog_row[4])
                cataloged_at = datetime.fromisoformat(str(catalog_row[1]).replace("Z", "+00:00"))
                if reconciled_at < cataloged_at:
                    raise ValueError("reconciliation cannot predate catalog")
                if cataloged_at <= plan.registered_at:
                    reasons.append("CATALOG_NOT_AFTER_PLAN")
                    corrupt = True
                if (
                    str(catalog_row[2]) != PACKAGE_VERSION
                    or catalog.get("code_version") != PACKAGE_VERSION
                ):
                    reasons.append("CATALOG_CODE_VERSION_MISMATCH")
                    corrupt = True
                if str(catalog_row[0]) != plan.catalog_name:
                    reasons.append("CATALOG_NAME_MISMATCH")
                raw_entries = catalog.get("entries")
                if not isinstance(raw_entries, list) or not all(
                    isinstance(entry, dict) for entry in raw_entries
                ):
                    raise ValueError("review catalog entries are corrupt")
                entries = tuple(
                    ReviewBundleCatalogEntry(
                        str(entry["bundle_id"]),
                        str(entry["verification_id"]),
                        str(entry["artifact_hash"]),
                        str(entry["manifest_payload_hash"]),
                        str(entry["verification_payload_hash"]),
                        str(entry["review_root_hash"]),
                        int(entry["review_count"]),
                        int(entry["active_review_count"]),
                        int(entry["summary_eligible_count"]),
                        _datetime(entry["verified_at"]),
                    )
                    for entry in raw_entries
                )
                stored_catalog = ReviewBundleCatalog(
                    str(catalog["catalog_id"]),
                    str(catalog["catalog_name"]),
                    _datetime(catalog["cataloged_at"]),
                    entries,
                    str(catalog["catalog_root_hash"]),
                    int(catalog["bundle_count"]),
                    int(catalog["total_review_count"]),
                    int(catalog["total_active_review_count"]),
                    int(catalog["total_summary_eligible_count"]),
                    str(catalog["source_revision"]),
                    str(catalog["code_version"]),
                    tuple(str(item) for item in catalog["disclosures"]),
                    str(catalog["config_hash"]),
                )
                expected_root = canonical_hash(
                    tuple(
                        (
                            entry.bundle_id,
                            entry.verification_id,
                            entry.manifest_payload_hash,
                            entry.verification_payload_hash,
                            entry.artifact_hash,
                        )
                        for entry in entries
                    )
                )
                if (
                    stored_catalog.catalog_id != catalog_id
                    or stored_catalog.catalog_name != str(catalog_row[0])
                    or _time(stored_catalog.cataloged_at) != str(catalog_row[1])
                    or stored_catalog.catalog_root_hash != expected_root
                ):
                    raise ValueError("review catalog parent evidence is corrupt")
                entry_rows = self.repository.connection.execute(
                    """SELECT bundle_id, verification_id, payload_json, payload_hash
                       FROM operations_observation_audit_review_catalog_entries
                       WHERE catalog_id = ? ORDER BY bundle_id""",
                    (catalog_id,),
                ).fetchall()
                if len(entry_rows) != len(entries):
                    raise ValueError("review catalog child entries are incomplete")
                for row_value, entry in zip(entry_rows, entries, strict=True):
                    if (
                        (str(row_value[0]), str(row_value[1]))
                        != (entry.bundle_id, entry.verification_id)
                        or canonical_json(entry) != str(row_value[2])
                        or canonical_hash(entry) != str(row_value[3])
                    ):
                        raise ValueError("review catalog child entry is corrupt")
                actual = {
                    entry.bundle_id: entry.verification_id for entry in entries
                }
                expected = {source.bundle_id: source.verification_id for source in plan.sources}
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
            except (KeyError, TypeError, ValueError):
                reasons.append("CATALOG_PAYLOAD_CORRUPT")
                corrupt = True
                catalog_hash = None
        return ReviewCatalogPlanReconciliation.create(
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

    def insert_reconciliation(self, result: ReviewCatalogPlanReconciliation) -> bool:
        payload_json = canonical_json(result)
        payload_hash = canonical_hash(result)
        values = (
            result.reconciliation_id,
            result.plan_id,
            result.catalog_id,
            _time(result.reconciled_at),
            result.status.value,
            result.source_revision,
            result.code_version,
            result.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_review_catalog_plan_reconciliations
               (reconciliation_id, plan_id, catalog_id, reconciled_at, status, source_revision,
                code_version, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT reconciliation_id, plan_id, catalog_id, reconciled_at, status,
                          source_revision, code_version, config_hash, payload_json, payload_hash
                   FROM operations_review_catalog_plan_reconciliations
                   WHERE reconciliation_id = ?""",
                (result.reconciliation_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(f"conflicting catalog reconciliation: {result.reconciliation_id}")
            return False
        self.repository.connection.commit()
        return True

    def reconciliation(self, reconciliation_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash
               FROM operations_review_catalog_plan_reconciliations
               WHERE reconciliation_id = ?""",
            (reconciliation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown review catalog reconciliation")
        return _root(str(row[0]), str(row[1]), "review catalog reconciliation")
