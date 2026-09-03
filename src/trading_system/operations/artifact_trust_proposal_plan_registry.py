"""Append-only Phase 6X prospective proposal plans and bindings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_policy_proposal_registry import (
    ArtifactTrustPolicyProposalRegistry,
)
from trading_system.operations.artifact_trust_proposal_plan_config import (
    ArtifactTrustProposalPlanConfig,
)
from trading_system.operations.artifact_trust_proposal_plan_contracts import (
    ArtifactTrustProposalBinding,
    ArtifactTrustProposalPlan,
    ArtifactTrustProposalSlot,
)
from trading_system.operations.artifact_trust_review_export_contracts import (
    ArtifactTrustReviewVerificationStatus,
)
from trading_system.operations.artifact_trust_review_export_registry import (
    ArtifactTrustReviewExportRegistry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proposal plan timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid proposal plan timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("proposal plan timestamp must be timezone-aware")
    return result


def _payload(text: str, digest: str, name: str) -> dict[str, Any]:
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


class ArtifactTrustProposalPlanRegistry:
    def __init__(self, repository: SQLiteRepository, config: ArtifactTrustProposalPlanConfig,
                 proposals: ArtifactTrustPolicyProposalRegistry,
                 review_exports: ArtifactTrustReviewExportRegistry) -> None:
        self.repository = repository
        self.config = config
        self.proposals = proposals
        self.review_exports = review_exports

    def create_plan(self, *, plan_name: str, review_export_id: str,
                    review_verification_id: str, registered_at: datetime,
                    slots: tuple[tuple[str, datetime, datetime], ...],
                    source_revision: str) -> ArtifactTrustProposalPlan:
        manifest = self.review_exports.manifest(review_export_id)
        verification = self.review_exports.verification(review_verification_id)
        if (verification.export_id != review_export_id
                or verification.status is not ArtifactTrustReviewVerificationStatus.VERIFIED
                or verification.reasons or verification.promoted
                or verification.expected_hash != manifest.artifact_hash
                or verification.actual_hash != manifest.artifact_hash):
            raise ValueError("proposal plan requires exact verified Phase 6T evidence")
        if registered_at < verification.verified_at:
            raise ValueError("proposal plan cannot predate Phase 6T verification")
        if not plan_name or not source_revision:
            raise ValueError("proposal plan name and source revision are required")
        canonical = tuple(sorted(ArtifactTrustProposalSlot(*item) for item in slots))
        root = canonical_hash(tuple((item.slot_id, item.opens_at, item.closes_at)
                                    for item in canonical))
        return ArtifactTrustProposalPlan.create(
            plan_name=plan_name, review_export_id=review_export_id,
            review_verification_id=review_verification_id, registered_at=registered_at,
            slots=canonical, slot_root_hash=root, source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ArtifactTrustProposalPlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("proposal plan configuration hash mismatch")
        expected = self.create_plan(
            plan_name=plan.plan_name,
            review_export_id=plan.review_export_id,
            review_verification_id=plan.review_verification_id,
            registered_at=plan.registered_at,
            slots=tuple((item.slot_id, item.opens_at, item.closes_at) for item in plan.slots),
            source_revision=plan.source_revision,
        )
        if plan != expected or plan.code_version != PACKAGE_VERSION:
            raise ValueError("proposal plan provenance mismatch")
        for slot in plan.slots:
            preexisting = self.repository.connection.execute(
                """SELECT 1 FROM operations_artifact_trust_policy_proposals
                WHERE review_export_id=? AND review_verification_id=?
                AND proposed_at>=? AND proposed_at<=? LIMIT 1""",
                (
                    plan.review_export_id,
                    plan.review_verification_id,
                    _time(slot.opens_at),
                    _time(slot.closes_at),
                ),
            ).fetchone()
            if preexisting is not None:
                raise ValueError("proposal content already exists inside a prospective slot")
        text, digest = canonical_json(plan), canonical_hash(plan)
        values = (plan.plan_id, plan.plan_name, plan.review_export_id,
                  plan.review_verification_id, _time(plan.registered_at), plan.slot_root_hash,
                  plan.source_revision, plan.code_version, plan.config_hash, text, digest)
        with self.repository.connection:
            cursor = self.repository.connection.execute(
                """INSERT OR IGNORE INTO operations_artifact_trust_proposal_plans
                (plan_id,plan_name,review_export_id,review_verification_id,registered_at,
                 slot_root_hash,source_revision,code_version,config_hash,payload_json,payload_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", values)
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT plan_id,plan_name,review_export_id,review_verification_id,
                    registered_at,slot_root_hash,source_revision,code_version,config_hash,
                    payload_json,payload_hash FROM operations_artifact_trust_proposal_plans
                    WHERE plan_id=?""", (plan.plan_id,)).fetchone()
                if stored != values:
                    raise ValueError("conflicting artifact trust proposal plan")
                return False
            for slot in plan.slots:
                self.repository.connection.execute(
                    """INSERT INTO operations_artifact_trust_proposal_slots
                    (plan_id,slot_id,opens_at,closes_at,payload_json,payload_hash)
                    VALUES (?,?,?,?,?,?)""",
                    (plan.plan_id, slot.slot_id, _time(slot.opens_at), _time(slot.closes_at),
                     canonical_json(slot), canonical_hash(slot)))
        return True

    def plan(self, plan_id: str) -> ArtifactTrustProposalPlan:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM
            operations_artifact_trust_proposal_plans WHERE plan_id=?""",
            (plan_id,)).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust proposal plan")
        value = _payload(str(row[0]), str(row[1]), "proposal plan")
        raw_slots = value.get("slots")
        if not isinstance(raw_slots, list) or not all(isinstance(item, dict) for item in raw_slots):
            raise ValueError("proposal plan slots are corrupt")
        slots = tuple(ArtifactTrustProposalSlot(str(item["slot_id"]),
                                                _datetime(item["opens_at"]),
                                                _datetime(item["closes_at"]))
                      for item in raw_slots)
        plan = ArtifactTrustProposalPlan(
            str(value["plan_id"]), str(value["plan_name"]), str(value["review_export_id"]),
            str(value["review_verification_id"]), _datetime(value["registered_at"]), slots,
            str(value["slot_root_hash"]), str(value["source_revision"]),
            str(value["code_version"]), tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = self.create_plan(
            plan_name=plan.plan_name, review_export_id=plan.review_export_id,
            review_verification_id=plan.review_verification_id, registered_at=plan.registered_at,
            slots=tuple((item.slot_id, item.opens_at, item.closes_at) for item in slots),
            source_revision=plan.source_revision,
        )
        children = self.repository.connection.execute(
            """SELECT slot_id,opens_at,closes_at,payload_json,payload_hash FROM
            operations_artifact_trust_proposal_slots WHERE plan_id=? ORDER BY slot_id""",
            (plan_id,)).fetchall()
        if plan != expected or plan.code_version != PACKAGE_VERSION or len(children) != len(slots):
            raise ValueError("artifact trust proposal plan provenance is corrupt")
        for stored, slot in zip(children, slots, strict=True):
            if ((str(stored[0]), str(stored[1]), str(stored[2]))
                    != (slot.slot_id, _time(slot.opens_at), _time(slot.closes_at))
                    or str(stored[3]) != canonical_json(slot)
                    or str(stored[4]) != canonical_hash(slot)):
                raise ValueError("artifact trust proposal slot is corrupt")
        return plan

    def bind(self, *, plan_id: str, slot_id: str, proposal_id: str,
             bound_at: datetime, source_revision: str) -> ArtifactTrustProposalBinding:
        plan = self.plan(plan_id)
        slot = next((item for item in plan.slots if item.slot_id == slot_id), None)
        if slot is None:
            raise ValueError("unknown artifact trust proposal slot")
        proposal = self.proposals.proposal(proposal_id)
        if (proposal.review_export_id, proposal.review_verification_id) != (
                plan.review_export_id, plan.review_verification_id):
            raise ValueError("proposal does not share exact Phase 6T plan evidence")
        if not slot.opens_at <= proposal.proposed_at <= slot.closes_at:
            raise ValueError("proposal was not created within its registered slot window")
        if not source_revision:
            raise ValueError("proposal binding source revision is required")
        row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_policy_proposals
            WHERE proposal_id=?""",
            (proposal_id,)).fetchone()
        if row is None:
            raise ValueError("proposal binding evidence is missing")
        return ArtifactTrustProposalBinding.create(
            plan_id=plan_id, slot_id=slot_id, proposal_id=proposal_id, bound_at=bound_at,
            proposed_at=proposal.proposed_at, proposal_payload_hash=str(row[0]),
            source_revision=source_revision, config=self.config,
        )

    def insert_binding(self, binding: ArtifactTrustProposalBinding) -> bool:
        if binding.config_hash != self.config.config_hash:
            raise ValueError("proposal binding configuration hash mismatch")
        expected = self.bind(
            plan_id=binding.plan_id,
            slot_id=binding.slot_id,
            proposal_id=binding.proposal_id,
            bound_at=binding.bound_at,
            source_revision=binding.source_revision,
        )
        if binding != expected or binding.code_version != PACKAGE_VERSION:
            raise ValueError("proposal binding provenance mismatch")
        text, digest = canonical_json(binding), canonical_hash(binding)
        values = (binding.binding_id, binding.plan_id, binding.slot_id, binding.proposal_id,
                  _time(binding.bound_at), binding.source_revision, binding.code_version,
                  binding.config_hash, text, digest)
        with self.repository.connection:
            stored = self.repository.connection.execute(
                """SELECT binding_id,plan_id,slot_id,proposal_id,bound_at,source_revision,
                code_version,config_hash,payload_json,payload_hash FROM
                operations_artifact_trust_proposal_bindings WHERE binding_id=?""",
                (binding.binding_id,)).fetchone()
            if stored is not None:
                if stored != values:
                    raise ValueError("conflicting artifact trust proposal binding")
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_artifact_trust_proposal_bindings
                WHERE plan_id=? AND (slot_id=? OR proposal_id=?)""",
                (binding.plan_id, binding.slot_id, binding.proposal_id)).fetchone()
            if collision is not None:
                raise ValueError("proposal slot or proposal is already bound")
            self.repository.connection.execute(
                """INSERT INTO operations_artifact_trust_proposal_bindings
                (binding_id,plan_id,slot_id,proposal_id,bound_at,source_revision,code_version,
                 config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?)""", values)
        return True

    def status(self, plan_id: str) -> dict[str, Any]:
        plan = self.plan(plan_id)
        rows = self.repository.connection.execute(
            """SELECT slot_id,proposal_id,payload_json,payload_hash FROM
            operations_artifact_trust_proposal_bindings WHERE plan_id=? ORDER BY slot_id""",
            (plan_id,)).fetchall()
        bindings: list[dict[str, Any]] = []
        for row in rows:
            value = _payload(str(row[2]), str(row[3]), "proposal binding")
            if (value.get("plan_id") != plan_id or value.get("slot_id") != str(row[0])
                    or value.get("proposal_id") != str(row[1])
                    or value.get("code_version") != PACKAGE_VERSION
                    or value.get("config_hash") != self.config.config_hash):
                raise ValueError("proposal binding evidence is corrupt")
            proposal = self.proposals.proposal(str(row[1]))
            source = self.repository.connection.execute(
                """SELECT payload_hash FROM operations_artifact_trust_policy_proposals
                WHERE proposal_id=?""",
                (proposal.proposal_id,)).fetchone()
            if source is None or value.get("proposal_payload_hash") != str(source[0]):
                raise ValueError("bound proposal payload has changed")
            bindings.append(value)
        resolved = {str(item["slot_id"]) for item in bindings}
        pending = [item.slot_id for item in plan.slots if item.slot_id not in resolved]
        return {"plan": plan, "bindings": bindings, "slot_count": len(plan.slots),
                "resolved_count": len(bindings), "pending_count": len(pending),
                "pending_slot_ids": pending, "complete": not pending,
                "complete_population_claim": False}
