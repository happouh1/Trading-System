"""Append-only Phase 5A readiness evidence persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.operations.contracts import ComponentEvidence, OperationsManifest
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class OperationsRegistry:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def insert_manifest(self, manifest: OperationsManifest) -> bool:
        return self._insert(
            "operations_manifests",
            "manifest_id",
            manifest.manifest_id,
            ("known_at", "status", "config_hash", "code_version", "source_revision"),
            (
                _time(manifest.known_at),
                manifest.status.value,
                manifest.config_hash,
                manifest.code_version,
                manifest.source_revision,
            ),
            manifest,
        )

    def insert_evidence(self, manifest_id: str, evidence: ComponentEvidence) -> bool:
        return self._insert(
            "operations_component_evidence",
            "evidence_id",
            evidence.evidence_id,
            (
                "manifest_id",
                "component",
                "database_label",
                "known_at",
                "status",
                "evidence_fingerprint",
            ),
            (
                manifest_id,
                evidence.component,
                evidence.database_label,
                _time(evidence.known_at),
                evidence.status.value,
                evidence.evidence_fingerprint,
            ),
            evidence,
        )

    def status(self, manifest_id: str) -> tuple[str, str, int]:
        row = self.repository.connection.execute(
            "SELECT payload_json, status FROM operations_manifests WHERE manifest_id = ?",
            (manifest_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown operations manifest: {manifest_id}")
        count = self.repository.connection.execute(
            "SELECT COUNT(*) FROM operations_component_evidence WHERE manifest_id = ?",
            (manifest_id,),
        ).fetchone()
        if count is None:
            raise ValueError("unable to count operations evidence")
        return str(row[0]), str(row[1]), int(count[0])

    def _insert(
        self,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        allowed = {"operations_manifests", "operations_component_evidence"}
        if table not in allowed:
            raise ValueError("unsupported operations registry table")
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        names = (identity_column, *columns, "payload_json", "payload_hash")
        placeholders = ",".join("?" for _ in names)
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(names)}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_hash FROM {table} WHERE {identity_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_hash,):
                raise ValueError(f"conflicting {table} payload")
            return False
        self.repository.connection.commit()
        return True
