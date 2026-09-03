"""Append-only Phase 6W proposal-catalog plans and reconciliation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_policy_proposal_registry import (
    ArtifactTrustPolicyProposalRegistry,
)
from trading_system.operations.artifact_trust_proposal_catalog_plan_config import (
    ArtifactTrustProposalCatalogPlanConfig,
)
from trading_system.operations.artifact_trust_proposal_catalog_plan_contracts import (
    ArtifactTrustProposalCatalogPlan,
    ArtifactTrustProposalCatalogPlanReconciliation,
    ArtifactTrustProposalCatalogPlanSource,
)
from trading_system.operations.artifact_trust_proposal_catalog_registry import (
    ArtifactTrustProposalCatalogRegistry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proposal catalog plan time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid proposal catalog plan timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("proposal catalog plan time must be timezone-aware")
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


class ArtifactTrustProposalCatalogPlanRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ArtifactTrustProposalCatalogPlanConfig,
        proposals: ArtifactTrustPolicyProposalRegistry,
        catalogs: ArtifactTrustProposalCatalogRegistry,
    ) -> None:
        self.repository = repository
        self.config = config
        self.proposals = proposals
        self.catalogs = catalogs

    def create_plan(
        self,
        *,
        proposal_ids: tuple[str, ...],
        registered_at: datetime,
        source_revision: str,
    ) -> ArtifactTrustProposalCatalogPlan:
        if not proposal_ids or proposal_ids != tuple(sorted(set(proposal_ids))):
            raise ValueError("planned proposal IDs must be nonempty, sorted, and unique")
        if registered_at.tzinfo is None or registered_at.utcoffset() is None:
            raise ValueError("proposal catalog plan time must be timezone-aware")
        if not source_revision:
            raise ValueError("proposal catalog plan source revision is required")
        sources: list[ArtifactTrustProposalCatalogPlanSource] = []
        for proposal_id in proposal_ids:
            proposal = self.proposals.proposal(proposal_id)
            if registered_at < proposal.proposed_at:
                raise ValueError("proposal catalog plan cannot predate a proposal")
            row = self.repository.connection.execute(
                """SELECT payload_hash FROM operations_artifact_trust_policy_proposals
                WHERE proposal_id=?""",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise ValueError("planned proposal evidence is missing")
            sources.append(ArtifactTrustProposalCatalogPlanSource(proposal_id, str(row[0])))
        canonical = tuple(sources)
        root = canonical_hash(
            tuple((item.proposal_id, item.proposal_payload_hash) for item in canonical)
        )
        return ArtifactTrustProposalCatalogPlan.create(
            registered_at=registered_at,
            sources=canonical,
            source_root_hash=root,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ArtifactTrustProposalCatalogPlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("proposal catalog plan config hash mismatch")
        text, digest = canonical_json(plan), canonical_hash(plan)
        values = (
            plan.plan_id,
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
                """INSERT OR IGNORE INTO operations_artifact_trust_proposal_catalog_plans
                (plan_id,registered_at,source_root_hash,source_revision,code_version,
                 config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = self.repository.connection.execute(
                    """SELECT plan_id,registered_at,source_root_hash,source_revision,
                    code_version,config_hash,payload_json,payload_hash
                    FROM operations_artifact_trust_proposal_catalog_plans WHERE plan_id=?""",
                    (plan.plan_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError("conflicting artifact trust proposal catalog plan")
                return False
            self.repository.connection.executemany(
                """INSERT INTO operations_artifact_trust_proposal_catalog_plan_sources
                (plan_id,proposal_id,proposal_payload_hash,payload_json,payload_hash)
                VALUES (?,?,?,?,?)""",
                (
                    (
                        plan.plan_id,
                        item.proposal_id,
                        item.proposal_payload_hash,
                        canonical_json(item),
                        canonical_hash(item),
                    )
                    for item in plan.sources
                ),
            )
        return True

    def plan(self, plan_id: str) -> ArtifactTrustProposalCatalogPlan:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
            FROM operations_artifact_trust_proposal_catalog_plans WHERE plan_id=?""",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust proposal catalog plan")
        value = _payload(str(row[0]), str(row[1]), "proposal catalog plan")
        raw_sources = value.get("sources")
        if not isinstance(raw_sources, list) or not all(
            isinstance(item, dict) for item in raw_sources
        ):
            raise ValueError("proposal catalog plan sources are corrupt")
        sources = tuple(
            ArtifactTrustProposalCatalogPlanSource(
                str(item["proposal_id"]), str(item["proposal_payload_hash"])
            )
            for item in raw_sources
        )
        plan = ArtifactTrustProposalCatalogPlan(
            str(value["plan_id"]),
            _datetime(value["registered_at"]),
            sources,
            str(value["source_root_hash"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = self.create_plan(
            proposal_ids=tuple(item.proposal_id for item in sources),
            registered_at=plan.registered_at,
            source_revision=plan.source_revision,
        )
        rows = self.repository.connection.execute(
            """SELECT proposal_id,proposal_payload_hash,payload_json,payload_hash
            FROM operations_artifact_trust_proposal_catalog_plan_sources
            WHERE plan_id=? ORDER BY proposal_id""",
            (plan_id,),
        ).fetchall()
        if plan != expected or plan.code_version != PACKAGE_VERSION or len(rows) != len(sources):
            raise ValueError("artifact trust proposal catalog plan provenance is corrupt")
        for stored, item in zip(rows, sources, strict=True):
            if (
                (str(stored[0]), str(stored[1]))
                != (item.proposal_id, item.proposal_payload_hash)
                or str(stored[2]) != canonical_json(item)
                or str(stored[3]) != canonical_hash(item)
            ):
                raise ValueError("artifact trust proposal catalog plan source is corrupt")
        return plan

    def reconcile(
        self,
        *,
        plan_id: str,
        catalog_id: str,
        reconciled_at: datetime,
        source_revision: str,
    ) -> ArtifactTrustProposalCatalogPlanReconciliation:
        plan = self.plan(plan_id)
        if reconciled_at < plan.registered_at:
            raise ValueError("proposal catalog reconciliation cannot predate plan")
        plan_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_proposal_catalog_plans
            WHERE plan_id=?""",
            (plan_id,),
        ).fetchone()
        assert plan_row is not None
        catalog_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_proposal_catalogs
            WHERE catalog_id=?""",
            (catalog_id,),
        ).fetchone()
        missing = catalog_row is None
        corrupt = False
        reasons: list[str] = []
        actual_count = 0
        catalog_hash: str | None = None
        if missing:
            reasons.append("CATALOG_MISSING")
        else:
            try:
                catalog = self.catalogs.catalog(catalog_id)
                catalog_hash = str(catalog_row[0])
                if reconciled_at < catalog.cataloged_at:
                    raise ValueError("proposal catalog reconciliation cannot predate catalog")
                if catalog.cataloged_at <= plan.registered_at:
                    reasons.append("CATALOG_NOT_AFTER_PLAN")
                    corrupt = True
                expected_ids = tuple(item.proposal_id for item in plan.sources)
                actual_count = len(catalog.proposal_ids)
                if set(expected_ids) - set(catalog.proposal_ids):
                    reasons.append("PLANNED_PROPOSAL_MISSING")
                if set(catalog.proposal_ids) - set(expected_ids):
                    reasons.append("UNPLANNED_PROPOSAL_PRESENT")
                if catalog.proposal_root_hash != plan.source_root_hash:
                    reasons.append("PROPOSAL_PAYLOAD_ROOT_CHANGED")
            except ValueError:
                reasons.append("CATALOG_PAYLOAD_CORRUPT")
                corrupt, catalog_hash = True, None
        return ArtifactTrustProposalCatalogPlanReconciliation.create(
            plan_id=plan_id,
            catalog_id=catalog_id,
            reconciled_at=reconciled_at,
            reasons=tuple(reasons),
            missing=missing,
            corrupt=corrupt,
            plan_payload_hash=str(plan_row[0]),
            catalog_payload_hash=catalog_hash,
            expected_proposal_count=len(plan.sources),
            actual_proposal_count=actual_count,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_reconciliation(
        self, result: ArtifactTrustProposalCatalogPlanReconciliation
    ) -> bool:
        if result.config_hash != self.config.config_hash:
            raise ValueError("proposal catalog reconciliation config hash mismatch")
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
            """INSERT OR IGNORE INTO operations_artifact_trust_proposal_catalog_reconciliations
            (reconciliation_id,plan_id,catalog_id,reconciled_at,status,source_revision,
             code_version,config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT reconciliation_id,plan_id,catalog_id,reconciled_at,status,
                source_revision,code_version,config_hash,payload_json,payload_hash
                FROM operations_artifact_trust_proposal_catalog_reconciliations
                WHERE reconciliation_id=?""",
                (result.reconciliation_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting artifact trust proposal catalog reconciliation")
            return False
        self.repository.connection.commit()
        return True

    def reconciliation(self, reconciliation_id: str) -> dict[str, Any]:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
            FROM operations_artifact_trust_proposal_catalog_reconciliations
            WHERE reconciliation_id=?""",
            (reconciliation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust proposal catalog reconciliation")
        return _payload(str(row[0]), str(row[1]), "proposal catalog reconciliation")
