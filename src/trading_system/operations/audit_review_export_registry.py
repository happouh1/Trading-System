"""Append-only Phase 6F review-bundle persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.operations.audit_review_export_config import (
    ObservationAuditReviewExportConfig,
)
from trading_system.operations.audit_review_export_contracts import (
    ReviewBundleManifest,
    ReviewBundleVerification,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("review bundle timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid canonical review bundle timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("review bundle timestamp must be timezone-aware")
    return result


class ObservationAuditReviewExportRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ObservationAuditReviewExportConfig
    ) -> None:
        self.repository = repository
        self.config = config

    def insert_manifest(self, manifest: ReviewBundleManifest) -> bool:
        if manifest.config_hash != self.config.config_hash:
            raise ValueError("review bundle configuration hash mismatch")
        payload_json = canonical_json(manifest)
        payload_hash = canonical_hash(manifest)
        values = (
            manifest.bundle_id,
            manifest.export_id,
            manifest.source_verification_id,
            _time(manifest.bundled_at),
            manifest.artifact_path,
            manifest.artifact_hash,
            manifest.artifact_bytes,
            manifest.export_manifest_hash,
            manifest.source_verification_hash,
            manifest.review_root_hash,
            manifest.review_count,
            manifest.active_review_count,
            manifest.summary_eligible_count,
            manifest.source_revision,
            manifest.code_version,
            manifest.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_observation_audit_review_bundles
               (bundle_id, export_id, source_verification_id, bundled_at, artifact_path,
                artifact_hash, artifact_bytes, export_manifest_hash, source_verification_hash,
                review_root_hash, review_count, active_review_count, summary_eligible_count,
                source_revision, code_version, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT bundle_id, export_id, source_verification_id, bundled_at,
                          artifact_path, artifact_hash, artifact_bytes, export_manifest_hash,
                          source_verification_hash, review_root_hash, review_count,
                          active_review_count, summary_eligible_count, source_revision,
                          code_version, config_hash, payload_json, payload_hash
                   FROM operations_observation_audit_review_bundles WHERE bundle_id = ?""",
                (manifest.bundle_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(f"conflicting review bundle: {manifest.bundle_id}")
            return False
        self.repository.connection.commit()
        return True

    def insert_verification(self, verification: ReviewBundleVerification) -> bool:
        if verification.config_hash != self.config.config_hash:
            raise ValueError("review bundle verification configuration hash mismatch")
        payload_json = canonical_json(verification)
        payload_hash = canonical_hash(verification)
        values = (
            verification.verification_id,
            verification.bundle_id,
            _time(verification.verified_at),
            verification.status.value,
            verification.source_revision,
            verification.code_version,
            verification.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_observation_audit_review_bundle_verifications
               (verification_id, bundle_id, verified_at, status, source_revision,
                code_version, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT verification_id, bundle_id, verified_at, status, source_revision,
                          code_version, config_hash, payload_json, payload_hash
                   FROM operations_observation_audit_review_bundle_verifications
                   WHERE verification_id = ?""",
                (verification.verification_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(
                    "conflicting review bundle verification: "
                    f"{verification.verification_id}"
                )
            return False
        self.repository.connection.commit()
        return True

    def manifest(self, bundle_id: str) -> ReviewBundleManifest:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash
               FROM operations_observation_audit_review_bundles WHERE bundle_id = ?""",
            (bundle_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation audit review bundle")
        try:
            value: object = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise ValueError("review bundle manifest payload is corrupt") from error
        if (
            not isinstance(value, dict)
            or canonical_json(value) != str(row[0])
            or canonical_hash(value) != str(row[1])
        ):
            raise ValueError("review bundle manifest payload is corrupt")
        manifest = ReviewBundleManifest(
            str(value["bundle_id"]),
            str(value["export_id"]),
            str(value["source_verification_id"]),
            _datetime(value["bundled_at"]),
            str(value["artifact_path"]),
            str(value["artifact_hash"]),
            int(value["artifact_bytes"]),
            str(value["export_manifest_hash"]),
            str(value["source_verification_hash"]),
            str(value["review_root_hash"]),
            int(value["review_count"]),
            int(value["active_review_count"]),
            int(value["summary_eligible_count"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        if manifest.config_hash != self.config.config_hash:
            raise ValueError("review bundle manifest configuration hash mismatch")
        return manifest

    def status(self, bundle_id: str) -> tuple[ReviewBundleManifest, str | None, int]:
        manifest = self.manifest(bundle_id)
        rows = self.repository.connection.execute(
            """SELECT status
               FROM operations_observation_audit_review_bundle_verifications
               WHERE bundle_id = ? ORDER BY verified_at, verification_id""",
            (bundle_id,),
        ).fetchall()
        return manifest, None if not rows else str(rows[-1][0]), len(rows)
