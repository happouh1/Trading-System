"""Append-only Phase 6S unresolved trust policies and signing requests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_config import ArtifactTrustConfig
from trading_system.operations.artifact_trust_contracts import (
    ArtifactSigningRequest,
    ArtifactSigningRequestStatus,
    ArtifactTrustPolicy,
    ArtifactTrustPolicyStatus,
)
from trading_system.operations.prospective_review_bundle_chain_export_config import (
    ProspectiveReviewBundleChainExportConfig,
)
from trading_system.operations.prospective_review_bundle_chain_export_registry import (
    ProspectiveReviewBundleChainExportRegistry,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("artifact trust time must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid artifact trust timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("artifact trust time must be timezone-aware")
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


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


class ArtifactTrustRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        config: ArtifactTrustConfig,
        export_config: ProspectiveReviewBundleChainExportConfig,
    ) -> None:
        self.repository = repository
        self.config = config
        self.exports = ProspectiveReviewBundleChainExportRegistry(repository, export_config)

    def create_policy(
        self, *, registered_at: datetime, source_revision: str
    ) -> ArtifactTrustPolicy:
        if not source_revision:
            raise ValueError("artifact trust policy source revision is required")
        return ArtifactTrustPolicy.create(
            registered_at=registered_at,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_policy(self, item: ArtifactTrustPolicy) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("artifact trust policy configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.policy_id,
            _time(item.registered_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_artifact_trust_policies
            (policy_id,registered_at,status,source_revision,code_version,config_hash,
             payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT policy_id,registered_at,status,source_revision,code_version,
                config_hash,payload_json,payload_hash FROM operations_artifact_trust_policies
                WHERE policy_id=?""",
                (item.policy_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting artifact trust policy")
            return False
        self.repository.connection.commit()
        return True

    def policy(self, policy_id: str) -> ArtifactTrustPolicy:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_artifact_trust_policies
            WHERE policy_id=?""",
            (policy_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact trust policy")
        value = _payload(str(row[0]), str(row[1]), "artifact trust policy")
        item = ArtifactTrustPolicy(
            str(value["policy_id"]),
            _datetime(value["registered_at"]),
            ArtifactTrustPolicyStatus(str(value["status"])),
            str(value["signature_algorithm"]),
            str(value["key_custody"]),
            str(value["signer_identity"]),
            str(value["trusted_timestamp_provider"]),
            str(value["revocation_policy"]),
            str(value["receiving_verifier"]),
            tuple(str(item) for item in value["blockers"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = ArtifactTrustPolicy.create(
            registered_at=item.registered_at,
            source_revision=item.source_revision,
            config=self.config,
        )
        if item != expected or item.code_version != PACKAGE_VERSION:
            raise ValueError("artifact trust policy provenance is corrupt")
        return item

    def request_signing(
        self,
        *,
        policy_id: str,
        export_id: str,
        export_verification_id: str,
        requested_at: datetime,
        source_revision: str,
    ) -> ArtifactSigningRequest:
        policy = self.policy(policy_id)
        manifest = self.exports.manifest(export_id)
        row = self.repository.connection.execute(
            """SELECT export_id,verified_at,status,payload_json,payload_hash FROM
            operations_prospective_review_bundle_chain_export_verifications
            WHERE verification_id=?""",
            (export_verification_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown Phase 6R export verification")
        verification = _payload(str(row[3]), str(row[4]), "Phase 6R verification")
        verified_at = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
        if (
            str(row[0]) != export_id
            or str(row[2]) != "VERIFIED"
            or verification.get("verification_id") != export_verification_id
            or verification.get("export_id") != export_id
            or verification.get("status") != "VERIFIED"
            or verification.get("reasons") != []
            or verification.get("promoted") is not False
            or verification.get("expected_hash") != manifest.artifact_hash
            or verification.get("actual_hash") != manifest.artifact_hash
            or verification.get("code_version") != PACKAGE_VERSION
        ):
            raise ValueError("signing request requires exact verified Phase 6R evidence")
        if requested_at < max(policy.registered_at, verified_at):
            raise ValueError("signing request cannot predate policy or verification")
        if not source_revision:
            raise ValueError("artifact signing request source revision is required")
        manifest_row = self.repository.connection.execute(
            """SELECT payload_hash FROM operations_prospective_review_bundle_chain_exports
            WHERE export_id=?""",
            (export_id,),
        ).fetchone()
        if manifest_row is None:
            raise ValueError("unknown Phase 6R export")
        return ArtifactSigningRequest.create(
            policy_id=policy_id,
            export_id=export_id,
            export_verification_id=export_verification_id,
            requested_at=requested_at,
            artifact_hash=manifest.artifact_hash,
            chain_root_hash=manifest.chain_root_hash,
            export_manifest_payload_hash=str(manifest_row[0]),
            export_verification_payload_hash=str(row[4]),
            source_revision=source_revision,
            config=self.config,
        )

    def insert_request(self, item: ArtifactSigningRequest) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("artifact signing request configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.request_id,
            item.policy_id,
            item.export_id,
            item.export_verification_id,
            _time(item.requested_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        with self.repository.connection:
            existing = self.repository.connection.execute(
                """SELECT request_id,policy_id,export_id,export_verification_id,requested_at,
                status,source_revision,code_version,config_hash,payload_json,payload_hash
                FROM operations_artifact_signing_requests WHERE request_id=?""",
                (item.request_id,),
            ).fetchone()
            if existing is not None:
                if existing != values:
                    raise ValueError("conflicting artifact signing request")
                return False
            collision = self.repository.connection.execute(
                """SELECT 1 FROM operations_artifact_signing_requests
                WHERE policy_id=? AND export_id=? AND export_verification_id=?""",
                (item.policy_id, item.export_id, item.export_verification_id),
            ).fetchone()
            if collision is not None:
                raise ValueError("Phase 6R evidence already has a request under this policy")
            self.repository.connection.execute(
                """INSERT INTO operations_artifact_signing_requests
                (request_id,policy_id,export_id,export_verification_id,requested_at,status,
                 source_revision,code_version,config_hash,payload_json,payload_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
        return True

    def request(self, request_id: str) -> ArtifactSigningRequest:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_artifact_signing_requests
            WHERE request_id=?""",
            (request_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact signing request")
        value = _payload(str(row[0]), str(row[1]), "artifact signing request")
        item = ArtifactSigningRequest(
            str(value["request_id"]),
            str(value["policy_id"]),
            str(value["export_id"]),
            str(value["export_verification_id"]),
            _datetime(value["requested_at"]),
            ArtifactSigningRequestStatus(str(value["status"])),
            str(value["artifact_hash"]),
            str(value["chain_root_hash"]),
            str(value["export_manifest_payload_hash"]),
            str(value["export_verification_payload_hash"]),
            tuple(str(item) for item in value["blockers"]),
            _boolean(value["signed"], "signed"),
            _boolean(value["trusted_timestamped"], "trusted timestamped"),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        expected = self.request_signing(
            policy_id=item.policy_id,
            export_id=item.export_id,
            export_verification_id=item.export_verification_id,
            requested_at=item.requested_at,
            source_revision=item.source_revision,
        )
        if item != expected or item.code_version != PACKAGE_VERSION:
            raise ValueError("artifact signing request provenance is corrupt")
        return item
