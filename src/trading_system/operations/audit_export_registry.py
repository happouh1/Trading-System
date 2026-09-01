"""Append-only Phase 6D audit-export manifest and verification repository."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system.operations.audit_export_config import ObservationAuditExportConfig
from trading_system.operations.audit_export_contracts import (
    AuditExportManifest,
    AuditExportVerification,
    AuditExportVerificationStatus,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("audit export timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, dict) or set(value) != {"__datetime__"}:
        raise ValueError("invalid canonical audit export timestamp")
    result = datetime.fromisoformat(str(value["__datetime__"]).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("audit export timestamp must be timezone-aware")
    return result


class ObservationAuditExportRegistry:
    def __init__(
        self, repository: SQLiteRepository, config: ObservationAuditExportConfig
    ) -> None:
        self.repository = repository
        self.config = config

    def insert_manifest(self, manifest: AuditExportManifest) -> bool:
        if manifest.config_hash != self.config.config_hash:
            raise ValueError("audit export configuration hash mismatch")
        payload_json = canonical_json(manifest)
        payload_hash = canonical_hash(manifest)
        values = (
            manifest.export_id,
            manifest.packet_id,
            _time(manifest.exported_at),
            manifest.artifact_path,
            manifest.artifact_hash,
            manifest.artifact_bytes,
            manifest.packet_payload_hash,
            manifest.artifact_root_hash,
            manifest.artifact_count,
            manifest.source_revision,
            manifest.code_version,
            manifest.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_observation_audit_exports
               (export_id, packet_id, exported_at, artifact_path, artifact_hash,
                artifact_bytes, packet_payload_hash, artifact_root_hash, artifact_count,
                source_revision, code_version, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT export_id, packet_id, exported_at, artifact_path, artifact_hash,
                          artifact_bytes, packet_payload_hash, artifact_root_hash, artifact_count,
                          source_revision, code_version, config_hash, payload_json, payload_hash
                   FROM operations_observation_audit_exports WHERE export_id = ?""",
                (manifest.export_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(f"conflicting observation audit export: {manifest.export_id}")
            return False
        self.repository.connection.commit()
        return True

    def insert_verification(self, verification: AuditExportVerification) -> bool:
        if verification.config_hash != self.config.config_hash:
            raise ValueError("audit export verification configuration hash mismatch")
        payload_json = canonical_json(verification)
        payload_hash = canonical_hash(verification)
        values = (
            verification.verification_id,
            verification.export_id,
            _time(verification.verified_at),
            verification.status.value,
            verification.source_revision,
            verification.code_version,
            verification.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_observation_audit_export_verifications
               (verification_id, export_id, verified_at, status, source_revision,
                code_version, config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT verification_id, export_id, verified_at, status, source_revision,
                          code_version, config_hash, payload_json, payload_hash
                   FROM operations_observation_audit_export_verifications
                   WHERE verification_id = ?""",
                (verification.verification_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(
                    f"conflicting audit export verification: {verification.verification_id}"
                )
            return False
        self.repository.connection.commit()
        return True

    def manifest(self, export_id: str) -> AuditExportManifest:
        row = self.repository.connection.execute(
            """SELECT payload_json, payload_hash FROM operations_observation_audit_exports
               WHERE export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation audit export")
        try:
            value: object = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise ValueError("audit export manifest payload is corrupt") from error
        if (
            not isinstance(value, dict)
            or canonical_json(value) != str(row[0])
            or canonical_hash(value) != str(row[1])
        ):
            raise ValueError("audit export manifest payload is corrupt")
        manifest = AuditExportManifest(
            str(value["export_id"]),
            str(value["packet_id"]),
            _datetime(value["exported_at"]),
            str(value["artifact_path"]),
            str(value["artifact_hash"]),
            int(value["artifact_bytes"]),
            str(value["packet_payload_hash"]),
            str(value["artifact_root_hash"]),
            int(value["artifact_count"]),
            str(value["reconciliation_status"]),
            str(value["campaign_status"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["disclosures"]),
            str(value["config_hash"]),
        )
        if manifest.config_hash != self.config.config_hash:
            raise ValueError("audit export manifest configuration hash mismatch")
        return manifest

    def status(self, export_id: str) -> tuple[AuditExportManifest, str | None, int]:
        manifest = self.manifest(export_id)
        rows = self.repository.connection.execute(
            """SELECT status FROM operations_observation_audit_export_verifications
               WHERE export_id = ? ORDER BY verified_at, verification_id""",
            (export_id,),
        ).fetchall()
        return manifest, None if not rows else str(rows[-1][0]), len(rows)


__all__ = [
    "AuditExportVerificationStatus",
    "ObservationAuditExportRegistry",
]
