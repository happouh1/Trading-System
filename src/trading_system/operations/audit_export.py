"""Deterministic local Phase 6D audit export and independent verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_export_config import ObservationAuditExportConfig
from trading_system.operations.audit_export_contracts import (
    AuditExportManifest,
    AuditExportVerification,
)
from trading_system.operations.audit_export_registry import ObservationAuditExportRegistry
from trading_system.serialization import canonical_hash, canonical_json


def _file_hash(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return value


def _contained(root: Path, relative: str, expected_directory: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) < 2:
        raise ValueError("audit export path is not contained")
    if pure.parts[0] != expected_directory:
        raise ValueError("audit export path is outside the configured directory")
    result = (root / Path(*pure.parts)).resolve()
    resolved_root = root.resolve()
    if resolved_root != result and resolved_root not in result.parents:
        raise ValueError("audit export path escapes its registry directory")
    return result


def _validate_envelope(value: object) -> tuple[str, str, int]:
    root = _object(value, "audit export envelope")
    if set(root) != {
        "schema_version",
        "packet_id",
        "packet_payload_hash",
        "artifact_root_hash",
        "reconciliation_status",
        "campaign_status",
        "packet",
        "artifacts",
    } or root["schema_version"] != "6D-AUDIT-EXPORT.1.0":
        raise ValueError("audit export envelope fields are invalid")
    packet = _object(root["packet"], "embedded audit packet")
    packet_hash = str(root["packet_payload_hash"])
    if canonical_hash(packet) != packet_hash or packet.get("packet_id") != root["packet_id"]:
        raise ValueError("embedded audit packet hash mismatch")
    if packet.get("reconciliation_status") != root["reconciliation_status"]:
        raise ValueError("embedded reconciliation status mismatch")
    if packet.get("campaign_status") != root["campaign_status"]:
        raise ValueError("embedded campaign status mismatch")
    raw_artifacts = root["artifacts"]
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("audit export artifacts must be a nonempty array")
    pairs: list[tuple[str, str]] = []
    names: list[str] = []
    for raw in raw_artifacts:
        artifact = _object(raw, "audit export artifact")
        if set(artifact) != {"name", "record_id", "payload", "payload_hash"}:
            raise ValueError("audit export artifact fields are invalid")
        name = str(artifact["name"])
        record_id = str(artifact["record_id"])
        payload_hash = str(artifact["payload_hash"])
        if not name or not record_id or canonical_hash(artifact["payload"]) != payload_hash:
            raise ValueError("audit export artifact hash mismatch")
        names.append(name)
        pairs.append((name, payload_hash))
    if names != sorted(set(names)):
        raise ValueError("audit export artifact order is not canonical")
    root_hash = canonical_hash(tuple(pairs))
    if root_hash != root["artifact_root_hash"] or root_hash != packet.get("artifact_root_hash"):
        raise ValueError("audit export artifact root mismatch")
    embedded = packet.get("artifacts")
    if not isinstance(embedded, list) or len(embedded) != len(raw_artifacts):
        raise ValueError("embedded audit packet artifact count mismatch")
    embedded_identity: list[tuple[object, object, object]] = []
    exported_identity: list[tuple[object, object, object]] = []
    for embedded_item, exported_item in zip(embedded, raw_artifacts, strict=True):
        if not isinstance(embedded_item, dict) or not isinstance(exported_item, dict):
            raise ValueError("embedded audit packet artifact is invalid")
        if set(embedded_item) != {
            "__type__",
            "name",
            "record_id",
            "payload_json",
            "payload_hash",
        } or embedded_item["__type__"] != "AuditArtifact":
            raise ValueError("embedded audit packet artifact fields are invalid")
        try:
            embedded_payload: object = json.loads(str(embedded_item["payload_json"]))
        except json.JSONDecodeError as error:
            raise ValueError("embedded audit artifact payload is invalid") from error
        if (
            canonical_json(embedded_payload) != embedded_item["payload_json"]
            or canonical_hash(embedded_payload) != embedded_item["payload_hash"]
            or canonical_json(exported_item["payload"]) != embedded_item["payload_json"]
        ):
            raise ValueError("embedded audit artifact payload mismatch")
        embedded_identity.append(
            (
                embedded_item["name"],
                embedded_item["record_id"],
                embedded_item["payload_hash"],
            )
        )
        exported_identity.append(
            (
                exported_item["name"],
                exported_item["record_id"],
                exported_item["payload_hash"],
            )
        )
    if embedded_identity != exported_identity:
        raise ValueError("embedded and exported audit artifacts differ")
    return packet_hash, root_hash, len(raw_artifacts)


class ObservationAuditExportService:
    def __init__(
        self,
        config: ObservationAuditExportConfig,
        registry: ObservationAuditExportRegistry,
    ) -> None:
        self.config = config
        self.registry = registry

    @property
    def _root(self) -> Path:
        if str(self.registry.repository.path) == ":memory:":
            raise ValueError("audit exports require a file-backed registry database")
        return self.registry.repository.path.resolve().parent

    def export(
        self,
        *,
        packet_id: str,
        exported_at: datetime,
        source_revision: str,
    ) -> AuditExportManifest:
        if not packet_id or not source_revision:
            raise ValueError("audit export packet ID and source revision are required")
        row = self.registry.repository.connection.execute(
            """SELECT created_at, reconciliation_status, campaign_status,
                      artifact_root_hash, code_version, payload_json, payload_hash
               FROM operations_observation_audit_packets WHERE packet_id = ?""",
            (packet_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation audit packet")
        created_at = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        if exported_at < created_at:
            raise ValueError("audit export cannot predate its packet")
        if str(row[4]) != PACKAGE_VERSION:
            raise ValueError("audit packet code version is not current")
        try:
            packet_value: object = json.loads(str(row[5]))
        except json.JSONDecodeError as error:
            raise ValueError("audit packet payload is corrupt") from error
        packet = _object(packet_value, "audit packet")
        if canonical_json(packet) != str(row[5]) or canonical_hash(packet) != str(row[6]):
            raise ValueError("audit packet payload is corrupt")
        if packet.get("packet_id") != packet_id or packet.get("code_version") != PACKAGE_VERSION:
            raise ValueError("audit packet identity or code version mismatch")
        artifact_rows = self.registry.repository.connection.execute(
            """SELECT artifact_name, record_id, payload_json, payload_hash
               FROM operations_observation_audit_artifacts
               WHERE packet_id = ? ORDER BY artifact_name""",
            (packet_id,),
        ).fetchall()
        artifacts: list[dict[str, object]] = []
        for artifact_row in artifact_rows:
            try:
                payload: object = json.loads(str(artifact_row[2]))
            except json.JSONDecodeError as error:
                raise ValueError("audit source artifact payload is corrupt") from error
            if (
                canonical_json(payload) != str(artifact_row[2])
                or canonical_hash(payload) != str(artifact_row[3])
            ):
                raise ValueError("audit source artifact payload is corrupt")
            artifacts.append(
                {
                    "name": str(artifact_row[0]),
                    "record_id": str(artifact_row[1]),
                    "payload": payload,
                    "payload_hash": str(artifact_row[3]),
                }
            )
        envelope = {
            "schema_version": "6D-AUDIT-EXPORT.1.0",
            "packet_id": packet_id,
            "packet_payload_hash": str(row[6]),
            "artifact_root_hash": str(row[3]),
            "reconciliation_status": str(row[1]),
            "campaign_status": str(row[2]),
            "packet": packet,
            "artifacts": artifacts,
        }
        packet_hash, root_hash, artifact_count = _validate_envelope(envelope)
        data = canonical_json(envelope).encode("utf-8")
        artifact_hash = _file_hash(data)
        relative = f"{self.config.export_directory}/{artifact_hash[7:]}.json"
        target = _contained(self._root, relative, self.config.export_directory)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or target.is_symlink() or target.read_bytes() != data:
                raise ValueError("content-addressed audit export has conflicting bytes")
        else:
            handle, staging_name = tempfile.mkstemp(
                prefix="audit-export-", suffix=".tmp", dir=target.parent
            )
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                Path(staging_name).replace(target)
            finally:
                staging = Path(staging_name)
                if staging.exists():
                    staging.unlink()
        manifest = AuditExportManifest.create(
            packet_id=packet_id,
            exported_at=exported_at,
            artifact_path=relative,
            artifact_hash=artifact_hash,
            artifact_bytes=len(data),
            packet_payload_hash=packet_hash,
            artifact_root_hash=root_hash,
            artifact_count=artifact_count,
            reconciliation_status=str(row[1]),
            campaign_status=str(row[2]),
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_manifest(manifest)
        return manifest

    def verify(
        self,
        *,
        export_id: str,
        verified_at: datetime,
        source_revision: str,
    ) -> AuditExportVerification:
        if not source_revision:
            raise ValueError("audit export verification source revision is required")
        manifest = self.registry.manifest(export_id)
        if verified_at < manifest.exported_at:
            raise ValueError("audit export verification cannot predate export")
        reasons: list[str] = []
        actual_hash: str | None = None
        try:
            artifact = _contained(
                self._root, manifest.artifact_path, self.config.export_directory
            )
            if not artifact.is_file() or artifact.is_symlink():
                reasons.append("EXPORT_ARTIFACT_MISSING_OR_UNSAFE")
            else:
                data = artifact.read_bytes()
                actual_hash = _file_hash(data)
                if actual_hash != manifest.artifact_hash:
                    reasons.append("EXPORT_FILE_HASH_MISMATCH")
                if len(data) != manifest.artifact_bytes:
                    reasons.append("EXPORT_FILE_SIZE_MISMATCH")
                try:
                    value: object = json.loads(data)
                    if canonical_json(value).encode("utf-8") != data:
                        reasons.append("EXPORT_JSON_NOT_CANONICAL")
                    packet_hash, root_hash, count = _validate_envelope(value)
                    if packet_hash != manifest.packet_payload_hash:
                        reasons.append("EXPORT_PACKET_HASH_MISMATCH")
                    if root_hash != manifest.artifact_root_hash:
                        reasons.append("EXPORT_ARTIFACT_ROOT_MISMATCH")
                    if count != manifest.artifact_count:
                        reasons.append("EXPORT_ARTIFACT_COUNT_MISMATCH")
                except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                    reasons.append("EXPORT_ENVELOPE_INVALID")
        except ValueError:
            reasons.append("EXPORT_PATH_UNSAFE")
        verification = AuditExportVerification.create(
            export_id=export_id,
            verified_at=verified_at,
            expected_hash=manifest.artifact_hash,
            actual_hash=actual_hash,
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )
        self.registry.insert_verification(verification)
        return verification


__all__ = ["ObservationAuditExportService"]
