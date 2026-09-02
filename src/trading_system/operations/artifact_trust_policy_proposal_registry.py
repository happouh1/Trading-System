"""Append-only Phase 6U unauthenticated policy-proposal persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_policy_proposal_config import (
    ArtifactTrustPolicyProposalConfig,
)
from trading_system.operations.artifact_trust_policy_proposal_contracts import (
    ArtifactTrustPolicyProposal,
    ArtifactTrustPolicyProposalStatus,
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
        raise ValueError("policy proposal timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid policy proposal timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("policy proposal timestamp must be timezone-aware")
    return result


def _payload(text: str, digest: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("policy proposal payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("policy proposal payload is corrupt")
    return value


class ArtifactTrustPolicyProposalRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ArtifactTrustPolicyProposalConfig,
        review_exports: ArtifactTrustReviewExportRegistry,
    ) -> None:
        self.repository = repository
        self.config = config
        self.review_exports = review_exports

    def create(
        self,
        *,
        review_export_id: str,
        review_verification_id: str,
        proposed_at: datetime,
        signature_algorithm: str,
        key_custody: str,
        signer_identity: str,
        trusted_timestamp_provider: str,
        revocation_policy: str,
        receiving_verifier: str,
        source_revision: str,
    ) -> ArtifactTrustPolicyProposal:
        manifest = self.review_exports.manifest(review_export_id)
        verification = self.review_exports.verification(review_verification_id)
        if (
            verification.export_id != review_export_id
            or verification.status is not ArtifactTrustReviewVerificationStatus.VERIFIED
            or verification.reasons
            or verification.promoted
            or verification.expected_hash != manifest.artifact_hash
            or verification.actual_hash != manifest.artifact_hash
        ):
            raise ValueError("proposal requires exact verified Phase 6T evidence")
        if proposed_at.tzinfo is None or proposed_at.utcoffset() is None:
            raise ValueError("policy proposal time must be timezone-aware")
        if proposed_at < verification.verified_at:
            raise ValueError("policy proposal cannot predate Phase 6T verification")
        if not source_revision:
            raise ValueError("policy proposal source revision is required")
        manifest_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_review_exports
            WHERE export_id=?""",
            (review_export_id,),
        ).fetchone()
        verification_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_artifact_trust_review_export_verifications
            WHERE verification_id=?""",
            (review_verification_id,),
        ).fetchone()
        if manifest_row is None or verification_row is None:
            raise ValueError("proposal source evidence is missing")
        return ArtifactTrustPolicyProposal.create(
            review_export_id=review_export_id,
            review_verification_id=review_verification_id,
            proposed_at=proposed_at,
            signature_algorithm=signature_algorithm,
            key_custody=key_custody,
            signer_identity=signer_identity,
            trusted_timestamp_provider=trusted_timestamp_provider,
            revocation_policy=revocation_policy,
            receiving_verifier=receiving_verifier,
            review_artifact_hash=manifest.artifact_hash,
            review_chain_root_hash=manifest.chain_root_hash,
            review_manifest_payload_hash=str(manifest_row[0]),
            review_verification_payload_hash=str(verification_row[0]),
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, item: ArtifactTrustPolicyProposal) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("policy proposal configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.proposal_id,
            item.review_export_id,
            item.review_verification_id,
            _time(item.proposed_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_artifact_trust_policy_proposals
            (proposal_id,review_export_id,review_verification_id,proposed_at,status,
             source_revision,code_version,config_hash,payload_json,payload_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT proposal_id,review_export_id,review_verification_id,proposed_at,status,
                source_revision,code_version,config_hash,payload_json,payload_hash
                FROM operations_artifact_trust_policy_proposals WHERE proposal_id=?""",
                (item.proposal_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting artifact trust policy proposal")
            return False
        self.repository.connection.commit()
        return True

    def proposal(self, proposal_id: str) -> ArtifactTrustPolicyProposal:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_artifact_trust_policy_proposals
            WHERE proposal_id=?""",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust policy proposal")
        value = _payload(str(row[0]), str(row[1]))
        item = ArtifactTrustPolicyProposal(
            str(value["proposal_id"]),
            str(value["review_export_id"]),
            str(value["review_verification_id"]),
            _datetime(value["proposed_at"]),
            ArtifactTrustPolicyProposalStatus(str(value["status"])),
            str(value["signature_algorithm"]),
            str(value["key_custody"]),
            str(value["signer_identity"]),
            str(value["trusted_timestamp_provider"]),
            str(value["revocation_policy"]),
            str(value["receiving_verifier"]),
            str(value["review_artifact_hash"]),
            str(value["review_chain_root_hash"]),
            str(value["review_manifest_payload_hash"]),
            str(value["review_verification_payload_hash"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(disclosure) for disclosure in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = self.create(
            review_export_id=item.review_export_id,
            review_verification_id=item.review_verification_id,
            proposed_at=item.proposed_at,
            signature_algorithm=item.signature_algorithm,
            key_custody=item.key_custody,
            signer_identity=item.signer_identity,
            trusted_timestamp_provider=item.trusted_timestamp_provider,
            revocation_policy=item.revocation_policy,
            receiving_verifier=item.receiving_verifier,
            source_revision=item.source_revision,
        )
        if item != expected or item.code_version != PACKAGE_VERSION:
            raise ValueError("artifact trust policy proposal provenance is corrupt")
        return item
