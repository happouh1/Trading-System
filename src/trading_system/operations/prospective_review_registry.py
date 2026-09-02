"""Append-only Phase 6I prospective review-slot plans and bindings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.prospective_review_config import ProspectiveReviewPlanConfig
from trading_system.operations.prospective_review_contracts import (
    ProspectiveReviewBinding,
    ProspectiveReviewPlan,
    ProspectiveReviewSlot,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("prospective review timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid canonical prospective review timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("prospective review timestamp must be timezone-aware")
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


class ProspectiveReviewPlanRegistry:
    def __init__(self, repository: SQLiteRepository, config: ProspectiveReviewPlanConfig) -> None:
        self.repository = repository
        self.config = config

    def create_plan(
        self,
        *,
        catalog_name: str,
        registered_at: datetime,
        slots: tuple[tuple[str, datetime], ...],
        source_revision: str,
    ) -> ProspectiveReviewPlan:
        canonical = tuple(
            sorted(ProspectiveReviewSlot(slot_id, expected) for slot_id, expected in slots)
        )
        root_hash = canonical_hash(tuple((slot.slot_id, slot.expected_as_of) for slot in canonical))
        return ProspectiveReviewPlan.create(
            catalog_name=catalog_name,
            registered_at=registered_at,
            slots=canonical,
            slot_root_hash=root_hash,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ProspectiveReviewPlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("prospective review plan configuration hash mismatch")
        payload_json, payload_hash = canonical_json(plan), canonical_hash(plan)
        values = (
            plan.plan_id,
            plan.catalog_name,
            _time(plan.registered_at),
            plan.slot_root_hash,
            plan.source_revision,
            plan.code_version,
            plan.config_hash,
            payload_json,
            payload_hash,
        )
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_prospective_review_plans
                   (plan_id,catalog_name,registered_at,slot_root_hash,source_revision,code_version,
                    config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT plan_id,catalog_name,registered_at,slot_root_hash,source_revision,
                              code_version,config_hash,payload_json,payload_hash
                       FROM operations_prospective_review_plans WHERE plan_id=?""",
                    (plan.plan_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(f"conflicting prospective review plan: {plan.plan_id}")
                return False
            for slot in plan.slots:
                self.repository.connection.execute(
                    """INSERT INTO operations_prospective_review_slots
                       (plan_id, slot_id, expected_as_of, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        plan.plan_id,
                        slot.slot_id,
                        _time(slot.expected_as_of),
                        canonical_json(slot),
                        canonical_hash(slot),
                    ),
                )
        return True

    def plan(self, plan_id: str) -> ProspectiveReviewPlan:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash
               FROM operations_prospective_review_plans WHERE plan_id = ?""",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown prospective review plan")
        value = _root(str(row[0]), str(row[1]), "prospective review plan")
        raw_slots = value.get("slots")
        if not isinstance(raw_slots, list) or not all(isinstance(slot, dict) for slot in raw_slots):
            raise ValueError("prospective review plan slots are corrupt")
        slots = tuple(
            ProspectiveReviewSlot(str(slot["slot_id"]), _datetime(slot["expected_as_of"]))
            for slot in raw_slots
        )
        plan = ProspectiveReviewPlan(
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
        expected_root = canonical_hash(tuple((slot.slot_id, slot.expected_as_of) for slot in slots))
        if (
            plan.config_hash != self.config.config_hash
            or plan.code_version != PACKAGE_VERSION
            or plan.slot_root_hash != expected_root
        ):
            raise ValueError("prospective review plan provenance mismatch")
        children = self.repository.connection.execute(
            """SELECT slot_id, expected_as_of, payload_json, payload_hash
               FROM operations_prospective_review_slots
               WHERE plan_id = ? ORDER BY slot_id""",
            (plan_id,),
        ).fetchall()
        if len(children) != len(slots):
            raise ValueError("prospective review plan child slots are incomplete")
        for stored, slot in zip(children, slots, strict=True):
            if (
                (str(stored[0]), str(stored[1])) != (slot.slot_id, _time(slot.expected_as_of))
                or canonical_json(slot) != str(stored[2])
                or canonical_hash(slot) != str(stored[3])
            ):
                raise ValueError("prospective review plan child slot is corrupt")
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
    ) -> ProspectiveReviewBinding:
        plan = self.plan(plan_id)
        if slot_id not in {slot.slot_id for slot in plan.slots}:
            raise ValueError("unknown prospective review slot")
        row = self.repository.connection.execute(
            """SELECT bundle_id, verified_at, status, code_version, payload_json, payload_hash
               FROM operations_observation_audit_review_bundle_verifications
               WHERE verification_id = ?""",
            (verification_id,),
        ).fetchone()
        bundle = self.repository.connection.execute(
            """SELECT code_version FROM operations_observation_audit_review_bundles
               WHERE bundle_id = ?""",
            (bundle_id,),
        ).fetchone()
        if row is None or bundle is None:
            raise ValueError("unknown prospective review binding evidence")
        verification = _root(str(row[4]), str(row[5]), "review bundle verification")
        verified_at = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
        if (
            str(row[0]) != bundle_id
            or str(row[2]) != "VERIFIED"
            or verification.get("status") != "VERIFIED"
            or verification.get("reasons") != []
            or verification.get("bundle_id") != bundle_id
            or verification.get("verification_id") != verification_id
        ):
            raise ValueError("binding requires exact VERIFIED bundle evidence")
        if str(row[3]) != PACKAGE_VERSION or str(bundle[0]) != PACKAGE_VERSION:
            raise ValueError("binding source code version is not current")
        if verified_at < plan.registered_at:
            raise ValueError("bundle verification predates prospective plan")
        if bound_at < verified_at:
            raise ValueError("binding cannot predate bundle verification")
        return ProspectiveReviewBinding.create(
            plan_id=plan_id,
            slot_id=slot_id,
            bundle_id=bundle_id,
            verification_id=verification_id,
            bound_at=bound_at,
            bundle_verified_at=verified_at,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_binding(self, binding: ProspectiveReviewBinding) -> bool:
        payload_json, payload_hash = canonical_json(binding), canonical_hash(binding)
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
            payload_json,
            payload_hash,
        )
        with self.repository.connection:
            stored = self.repository.connection.execute(
                """SELECT binding_id,plan_id,slot_id,bundle_id,verification_id,bound_at,
                          source_revision,code_version,config_hash,payload_json,payload_hash
                   FROM operations_prospective_review_bindings WHERE binding_id=?""",
                (binding.binding_id,),
            ).fetchone()
            if stored is not None:
                if stored != values:
                    raise ValueError(
                        f"conflicting prospective review binding: {binding.binding_id}"
                    )
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_prospective_review_bindings
                   WHERE plan_id = ? AND (slot_id = ? OR bundle_id = ?)""",
                (binding.plan_id, binding.slot_id, binding.bundle_id),
            ).fetchone()
            if collision is not None:
                raise ValueError("prospective review slot or bundle is already bound")
            self.repository.connection.execute(
                """INSERT INTO operations_prospective_review_bindings
                       (binding_id, plan_id, slot_id, bundle_id, verification_id, bound_at,
                        source_revision, code_version, config_hash, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
        return True

    def status(self, plan_id: str) -> dict[str, Any]:
        plan = self.plan(plan_id)
        rows = self.repository.connection.execute(
            """SELECT slot_id, bundle_id, verification_id, payload_json, payload_hash
               FROM operations_prospective_review_bindings
               WHERE plan_id = ? ORDER BY slot_id""",
            (plan_id,),
        ).fetchall()
        bindings: list[ProspectiveReviewBinding] = []
        for row in rows:
            value = _root(str(row[3]), str(row[4]), "prospective review binding")
            binding = ProspectiveReviewBinding(
                str(value["binding_id"]),
                str(value["plan_id"]),
                str(value["slot_id"]),
                str(value["bundle_id"]),
                str(value["verification_id"]),
                _datetime(value["bound_at"]),
                _datetime(value["bundle_verified_at"]),
                str(value["source_revision"]),
                str(value["code_version"]),
                tuple(str(item) for item in value["disclosures"]),
                str(value["config_hash"]),
            )
            if (
                (binding.slot_id, binding.bundle_id, binding.verification_id)
                != (str(row[0]), str(row[1]), str(row[2]))
                or binding.plan_id != plan_id
                or binding.code_version != PACKAGE_VERSION
                or binding.config_hash != self.config.config_hash
            ):
                raise ValueError("prospective review binding child evidence is corrupt")
            bindings.append(binding)
        resolved = {binding.slot_id for binding in bindings}
        pending = [slot.slot_id for slot in plan.slots if slot.slot_id not in resolved]
        return {
            "plan": plan,
            "bindings": bindings,
            "slot_count": len(plan.slots),
            "resolved_count": len(bindings),
            "pending_count": len(pending),
            "pending_slot_ids": pending,
            "complete": not pending,
        }
