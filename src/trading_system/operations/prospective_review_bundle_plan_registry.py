"""Append-only Phase 6P prospective review-bundle plans and bindings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_chain_review_catalog_config import (
    ProspectiveChainReviewCatalogConfig,
)
from trading_system.operations.prospective_chain_review_catalog_registry import (
    ProspectiveChainReviewCatalogRegistry,
)
from trading_system.operations.prospective_review_bundle_plan_config import (
    ProspectiveReviewBundlePlanConfig,
)
from trading_system.operations.prospective_review_bundle_plan_contracts import (
    ProspectiveReviewBundleBinding,
    ProspectiveReviewBundlePlan,
    ProspectiveReviewBundleSlot,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review-bundle plan time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid review-bundle plan timestamp")
    return datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))


def _root(text: str, digest: str, name: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError(f"{name} payload is corrupt")
    return value


class ProspectiveReviewBundlePlanRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ProspectiveReviewBundlePlanConfig,
        catalog_config: ProspectiveChainReviewCatalogConfig,
    ) -> None:
        self.repository, self.config, self.catalog_config = repository, config, catalog_config

    def create_plan(
        self,
        *,
        catalog_name: str,
        registered_at: datetime,
        slots: tuple[tuple[str, datetime], ...],
        source_revision: str,
    ) -> ProspectiveReviewBundlePlan:
        canonical = tuple(sorted(ProspectiveReviewBundleSlot(*item) for item in slots))
        root = canonical_hash(tuple((item.slot_id, item.expected_as_of) for item in canonical))
        return ProspectiveReviewBundlePlan.create(
            catalog_name=catalog_name,
            registered_at=registered_at,
            slots=canonical,
            slot_root_hash=root,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ProspectiveReviewBundlePlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("review-bundle plan config hash mismatch")
        text, digest = canonical_json(plan), canonical_hash(plan)
        values = (
            plan.plan_id,
            plan.catalog_name,
            _time(plan.registered_at),
            plan.slot_root_hash,
            plan.source_revision,
            plan.code_version,
            plan.config_hash,
            text,
            digest,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_prospective_review_bundle_plans
                (plan_id,catalog_name,registered_at,slot_root_hash,source_revision,code_version,
                 config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT plan_id,catalog_name,registered_at,slot_root_hash,source_revision,
                    code_version,config_hash,payload_json,payload_hash FROM
                    operations_prospective_review_bundle_plans WHERE plan_id=?""",
                    (plan.plan_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError("conflicting review-bundle plan")
                return False
            for slot in plan.slots:
                self.repository.connection.execute(
                    """INSERT INTO operations_prospective_review_bundle_slots
                    (plan_id,slot_id,expected_as_of,payload_json,payload_hash)
                    VALUES (?,?,?,?,?)""",
                    (
                        plan.plan_id,
                        slot.slot_id,
                        _time(slot.expected_as_of),
                        canonical_json(slot),
                        canonical_hash(slot),
                    ),
                )
        return True

    def plan(self, plan_id: str) -> ProspectiveReviewBundlePlan:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
               FROM operations_prospective_review_bundle_plans WHERE plan_id=?""",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown review-bundle plan")
        value = _root(str(row[0]), str(row[1]), "review-bundle plan")
        raw = value.get("slots")
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise ValueError("review-bundle plan slots are corrupt")
        slots = tuple(
            ProspectiveReviewBundleSlot(str(item["slot_id"]), _datetime(item["expected_as_of"]))
            for item in raw
        )
        plan = ProspectiveReviewBundlePlan(
            str(value["plan_id"]),
            str(value["catalog_name"]),
            _datetime(value["registered_at"]),
            slots,
            str(value["slot_root_hash"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = canonical_hash(tuple((item.slot_id, item.expected_as_of) for item in slots))
        if (
            plan.code_version != PACKAGE_VERSION
            or plan.config_hash != self.config.config_hash
            or plan.slot_root_hash != expected
        ):
            raise ValueError("review-bundle plan provenance mismatch")
        children = self.repository.connection.execute(
            """SELECT slot_id,expected_as_of,payload_json,payload_hash FROM
            operations_prospective_review_bundle_slots WHERE plan_id=? ORDER BY slot_id""",
            (plan_id,),
        ).fetchall()
        if len(children) != len(slots):
            raise ValueError("review-bundle plan slots are incomplete")
        for stored, slot in zip(children, slots, strict=True):
            if (
                (str(stored[0]), str(stored[1])) != (slot.slot_id, _time(slot.expected_as_of))
                or canonical_json(slot) != str(stored[2])
                or canonical_hash(slot) != str(stored[3])
            ):
                raise ValueError("review-bundle plan slot is corrupt")
        return plan

    def bind(
        self,
        *,
        plan_id: str,
        slot_id: str,
        bundle_id: str,
        verification_id: str,
        bound_at: datetime,
        source_revision: str,
    ) -> ProspectiveReviewBundleBinding:
        plan = self.plan(plan_id)
        if slot_id not in {item.slot_id for item in plan.slots}:
            raise ValueError("unknown review-bundle slot")
        entry = (
            ProspectiveChainReviewCatalogRegistry(self.repository, self.catalog_config)
            .create(
                catalog_name="phase6p-binding-validation",
                cataloged_at=bound_at,
                sources=((bundle_id, verification_id),),
                source_revision=source_revision,
            )
            .entries[0]
        )
        if entry.verified_at < plan.registered_at:
            raise ValueError("bundle verification predates review-bundle plan")
        return ProspectiveReviewBundleBinding.create(
            plan_id=plan_id,
            slot_id=slot_id,
            bundle_id=bundle_id,
            verification_id=verification_id,
            bound_at=bound_at,
            bundle_verified_at=entry.verified_at,
            artifact_hash=entry.artifact_hash,
            chain_root_hash=entry.chain_root_hash,
            review_root_hash=entry.review_root_hash,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_binding(self, binding: ProspectiveReviewBundleBinding) -> bool:
        text, digest = canonical_json(binding), canonical_hash(binding)
        values = (
            binding.binding_id,
            binding.plan_id,
            binding.slot_id,
            binding.bundle_id,
            binding.verification_id,
            _time(binding.bound_at),
            binding.source_revision,
            binding.code_version,
            binding.config_hash,
            text,
            digest,
        )
        with self.repository.connection:
            stored = self.repository.connection.execute(
                """SELECT binding_id,plan_id,slot_id,bundle_id,verification_id,bound_at,
                source_revision,code_version,config_hash,payload_json,payload_hash FROM
                operations_prospective_review_bundle_bindings WHERE binding_id=?""",
                (binding.binding_id,),
            ).fetchone()
            if stored is not None:
                if stored != values:
                    raise ValueError("conflicting review-bundle binding")
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_prospective_review_bundle_bindings
                WHERE plan_id=? AND (slot_id=? OR bundle_id=?)""",
                (binding.plan_id, binding.slot_id, binding.bundle_id),
            ).fetchone()
            if collision is not None:
                raise ValueError("review-bundle slot or bundle is already bound")
            self.repository.connection.execute(
                """INSERT INTO operations_prospective_review_bundle_bindings
                (binding_id,plan_id,slot_id,bundle_id,verification_id,bound_at,source_revision,
                 code_version,config_hash,payload_json,payload_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
        return True

    def status(self, plan_id: str) -> dict[str, Any]:
        plan = self.plan(plan_id)
        rows = self.repository.connection.execute(
            """SELECT slot_id,payload_json,payload_hash FROM
            operations_prospective_review_bundle_bindings WHERE plan_id=? ORDER BY slot_id""",
            (plan_id,),
        ).fetchall()
        bindings = [_root(str(row[1]), str(row[2]), "review-bundle binding") for row in rows]
        if any(
            item.get("plan_id") != plan_id
            or item.get("slot_id") != str(row[0])
            or item.get("code_version") != PACKAGE_VERSION
            or item.get("config_hash") != self.config.config_hash
            for row, item in zip(rows, bindings, strict=True)
        ):
            raise ValueError("review-bundle binding is corrupt")
        resolved = {str(item["slot_id"]) for item in bindings}
        pending = [item.slot_id for item in plan.slots if item.slot_id not in resolved]
        return {
            "plan": plan,
            "bindings": bindings,
            "slot_count": len(plan.slots),
            "resolved_count": len(bindings),
            "pending_count": len(pending),
            "pending_slot_ids": pending,
            "complete": not pending,
        }
