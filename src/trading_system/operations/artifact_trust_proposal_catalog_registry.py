"""Append-only Phase 6V descriptive proposal-catalog persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_policy_proposal_contracts import POLICY_FIELDS
from trading_system.operations.artifact_trust_policy_proposal_registry import (
    ArtifactTrustPolicyProposalRegistry,
)
from trading_system.operations.artifact_trust_proposal_catalog_config import (
    ArtifactTrustProposalCatalogConfig,
)
from trading_system.operations.artifact_trust_proposal_catalog_contracts import (
    ArtifactTrustProposalCatalog,
    ArtifactTrustProposalCatalogStatus,
    PolicyFieldComparison,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("catalog timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid catalog timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("catalog timestamp must be timezone-aware")
    return result


def _payload(text: str, digest: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("proposal catalog payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("proposal catalog payload is corrupt")
    return value


class ArtifactTrustProposalCatalogRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ArtifactTrustProposalCatalogConfig,
        proposals: ArtifactTrustPolicyProposalRegistry,
    ) -> None:
        self.repository = repository
        self.config = config
        self.proposals = proposals

    def create(
        self, *, proposal_ids: tuple[str, ...], cataloged_at: datetime, source_revision: str
    ) -> ArtifactTrustProposalCatalog:
        if not proposal_ids or proposal_ids != tuple(sorted(set(proposal_ids))):
            raise ValueError("proposal IDs must be nonempty, sorted, and unique")
        if cataloged_at.tzinfo is None or cataloged_at.utcoffset() is None:
            raise ValueError("catalog time must be timezone-aware")
        if not source_revision:
            raise ValueError("catalog source revision is required")
        proposals = tuple(self.proposals.proposal(item) for item in proposal_ids)
        first = proposals[0]
        if any(
            (item.review_export_id, item.review_verification_id)
            != (first.review_export_id, first.review_verification_id)
            for item in proposals
        ):
            raise ValueError("catalog proposals must share exact Phase 6T evidence")
        if any(cataloged_at < item.proposed_at for item in proposals):
            raise ValueError("catalog cannot predate a proposal")
        hashes: list[tuple[str, str]] = []
        for proposal_id in proposal_ids:
            row = self.repository.connection.execute(
                """SELECT payload_hash FROM operations_artifact_trust_policy_proposals
                WHERE proposal_id=?""",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise ValueError("catalog proposal evidence is missing")
            hashes.append((proposal_id, str(row[0])))
        comparisons = tuple(
            PolicyFieldComparison(
                field,
                tuple((item.proposal_id, str(getattr(item, field))) for item in proposals),
                len({str(getattr(item, field)) for item in proposals}) == 1,
            )
            for field in POLICY_FIELDS
        )
        return ArtifactTrustProposalCatalog.create(
            review_export_id=first.review_export_id,
            review_verification_id=first.review_verification_id,
            cataloged_at=cataloged_at,
            proposal_ids=proposal_ids,
            proposal_root_hash=canonical_hash(tuple(hashes)),
            comparisons=comparisons,
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, item: ArtifactTrustProposalCatalog) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("proposal catalog configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.catalog_id,
            item.review_export_id,
            item.review_verification_id,
            _time(item.cataloged_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_artifact_trust_proposal_catalogs
            (catalog_id,review_export_id,review_verification_id,cataloged_at,status,
             source_revision,code_version,config_hash,payload_json,payload_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT catalog_id,review_export_id,review_verification_id,cataloged_at,status,
                source_revision,code_version,config_hash,payload_json,payload_hash
                FROM operations_artifact_trust_proposal_catalogs WHERE catalog_id=?""",
                (item.catalog_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting artifact trust proposal catalog")
            return False
        self.repository.connection.executemany(
            """INSERT INTO operations_artifact_trust_proposal_catalog_entries
            (catalog_id,proposal_id,sequence) VALUES (?,?,?)""",
            (
                (item.catalog_id, proposal_id, sequence)
                for sequence, proposal_id in enumerate(item.proposal_ids)
            ),
        )
        self.repository.connection.commit()
        return True

    def catalog(self, catalog_id: str) -> ArtifactTrustProposalCatalog:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash
            FROM operations_artifact_trust_proposal_catalogs WHERE catalog_id=?""",
            (catalog_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust proposal catalog")
        value = _payload(str(row[0]), str(row[1]))
        comparisons = tuple(
            PolicyFieldComparison(
                str(item["field_name"]),
                tuple((str(pair[0]), str(pair[1])) for pair in item["proposal_values"]),
                bool(item["all_values_identical"]),
            )
            for item in value["comparisons"]
        )
        item = ArtifactTrustProposalCatalog(
            str(value["catalog_id"]),
            str(value["review_export_id"]),
            str(value["review_verification_id"]),
            _datetime(value["cataloged_at"]),
            tuple(str(item) for item in value["proposal_ids"]),
            str(value["proposal_root_hash"]),
            comparisons,
            ArtifactTrustProposalCatalogStatus(str(value["status"])),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = self.create(
            proposal_ids=item.proposal_ids,
            cataloged_at=item.cataloged_at,
            source_revision=item.source_revision,
        )
        entries = self.repository.connection.execute(
            """SELECT proposal_id FROM operations_artifact_trust_proposal_catalog_entries
            WHERE catalog_id=? ORDER BY sequence""",
            (catalog_id,),
        ).fetchall()
        if (
            item != expected
            or item.code_version != PACKAGE_VERSION
            or tuple(str(r[0]) for r in entries) != item.proposal_ids
        ):
            raise ValueError("artifact trust proposal catalog provenance is corrupt")
        return item
