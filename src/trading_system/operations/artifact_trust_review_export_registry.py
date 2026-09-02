"""Append-only Phase 6T artifact-trust review export persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.artifact_trust_review_export_config import (
    ArtifactTrustReviewExportConfig,
)
from trading_system.operations.artifact_trust_review_export_contracts import (
    ArtifactTrustReviewExportManifest,
    ArtifactTrustReviewExportVerification,
    ArtifactTrustReviewVerificationStatus,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("trust review timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid trust review timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("trust review timestamp must be timezone-aware")
    return result


def _payload(text: str, digest: str) -> dict[str, Any]:
    try:
        value: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("trust review export payload is corrupt") from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != text
        or canonical_hash(value) != digest
    ):
        raise ValueError("trust review export payload is corrupt")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


class ArtifactTrustReviewExportRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ArtifactTrustReviewExportConfig
    ) -> None:
        self.repository = repository
        self.config = config

    def insert_manifest(self, item: ArtifactTrustReviewExportManifest) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("trust review export configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.export_id,
            item.signing_request_id,
            _time(item.exported_at),
            item.artifact_path,
            item.artifact_hash,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_artifact_trust_review_exports
            (export_id,signing_request_id,exported_at,artifact_path,artifact_hash,
             source_revision,code_version,config_hash,payload_json,payload_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT export_id,signing_request_id,exported_at,artifact_path,artifact_hash,
                source_revision,code_version,config_hash,payload_json,payload_hash
                FROM operations_artifact_trust_review_exports WHERE export_id=?""",
                (item.export_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting trust review export")
            return False
        self.repository.connection.commit()
        return True

    def manifest(self, export_id: str) -> ArtifactTrustReviewExportManifest:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM operations_artifact_trust_review_exports
            WHERE export_id=?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown trust review export")
        value = _payload(str(row[0]), str(row[1]))
        item = ArtifactTrustReviewExportManifest(
            str(value["export_id"]),
            str(value["signing_request_id"]),
            _datetime(value["exported_at"]),
            str(value["artifact_path"]),
            str(value["artifact_hash"]),
            int(value["artifact_bytes"]),
            str(value["chain_root_hash"]),
            int(value["source_count"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        if item.config_hash != self.config.config_hash or item.code_version != PACKAGE_VERSION:
            raise ValueError("trust review export provenance mismatch")
        return item

    def insert_verification(self, item: ArtifactTrustReviewExportVerification) -> bool:
        if item.config_hash != self.config.config_hash:
            raise ValueError("trust review verification configuration hash mismatch")
        payload, digest = canonical_json(item), canonical_hash(item)
        values = (
            item.verification_id,
            item.export_id,
            _time(item.verified_at),
            item.status.value,
            item.source_revision,
            item.code_version,
            item.config_hash,
            payload,
            digest,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_artifact_trust_review_export_verifications
            (verification_id,export_id,verified_at,status,source_revision,code_version,
             config_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT verification_id,export_id,verified_at,status,source_revision,
                code_version,config_hash,payload_json,payload_hash FROM
                operations_artifact_trust_review_export_verifications WHERE verification_id=?""",
                (item.verification_id,),
            ).fetchone()
            if stored != values:
                raise ValueError("conflicting trust review verification")
            return False
        self.repository.connection.commit()
        return True

    def verification(self, verification_id: str) -> ArtifactTrustReviewExportVerification:
        row = self.repository.connection.execute(
            """SELECT payload_json,payload_hash FROM
            operations_artifact_trust_review_export_verifications WHERE verification_id=?""",
            (verification_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown trust review verification")
        value = _payload(str(row[0]), str(row[1]))
        actual = value["actual_hash"]
        item = ArtifactTrustReviewExportVerification(
            str(value["verification_id"]),
            str(value["export_id"]),
            _datetime(value["verified_at"]),
            ArtifactTrustReviewVerificationStatus(str(value["status"])),
            str(value["expected_hash"]),
            None if actual is None else str(actual),
            tuple(str(item) for item in value["reasons"]),
            _boolean(value["promoted"], "promoted"),
            str(value["source_revision"]),
            str(value["code_version"]),
            str(value["config_hash"]),
        )
        if item.config_hash != self.config.config_hash or item.code_version != PACKAGE_VERSION:
            raise ValueError("trust review verification provenance mismatch")
        return item

    def status(
        self, export_id: str
    ) -> tuple[ArtifactTrustReviewExportManifest, str | None, int]:
        manifest = self.manifest(export_id)
        rows = self.repository.connection.execute(
            """SELECT status FROM operations_artifact_trust_review_export_verifications
            WHERE export_id=? ORDER BY verified_at,verification_id""",
            (export_id,),
        ).fetchall()
        return manifest, None if not rows else str(rows[-1][0]), len(rows)
