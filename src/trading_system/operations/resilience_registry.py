"""Append-only Phase 5E resilience evidence repository."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from trading_system.operations.resilience_config import OperationsResilienceConfig
from trading_system.operations.resilience_contracts import (
    BackupManifest,
    RestoreVerification,
    RetentionReport,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("resilience timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class OperationsResilienceRegistry:
    def __init__(self, repository: SQLiteRepository, config: OperationsResilienceConfig) -> None:
        self.repository = repository
        self.config = config

    def _insert(
        self,
        table: str,
        id_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: object,
    ) -> bool:
        payload_json = canonical_json(payload)
        payload_hash = canonical_hash(payload)
        names = (id_column, *columns, "payload_json", "payload_hash")
        placeholders = ",".join("?" for _ in names)
        cursor = self.repository.connection.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(names)}) VALUES ({placeholders})",
            (identity, *values, payload_json, payload_hash),
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                f"SELECT payload_json, payload_hash FROM {table} WHERE {id_column} = ?",
                (identity,),
            ).fetchone()
            if stored != (payload_json, payload_hash):
                raise ValueError(f"conflicting resilience payload: {identity}")
            return False
        self.repository.connection.commit()
        return True

    def insert_backup(self, manifest: BackupManifest) -> bool:
        if manifest.config_hash != self.config.config_hash:
            raise ValueError("backup configuration hash mismatch")
        return self._insert(
            "operations_backup_manifests",
            "backup_id",
            manifest.backup_id,
            (
                "known_at",
                "source_path",
                "artifact_path",
                "artifact_hash",
                "artifact_bytes",
                "source_revision",
                "code_version",
                "config_hash",
            ),
            (
                _time(manifest.known_at),
                manifest.source_path,
                manifest.artifact_path,
                manifest.artifact_hash,
                manifest.artifact_bytes,
                manifest.source_revision,
                manifest.code_version,
                manifest.config_hash,
            ),
            manifest,
        )

    def insert_verification(self, verification: RestoreVerification) -> bool:
        if verification.config_hash != self.config.config_hash:
            raise ValueError("restore configuration hash mismatch")
        return self._insert(
            "operations_restore_verifications",
            "verification_id",
            verification.verification_id,
            ("backup_id", "known_at", "restored_path", "status", "config_hash"),
            (
                verification.backup_id,
                _time(verification.known_at),
                verification.restored_path,
                verification.status.value,
                verification.config_hash,
            ),
            verification,
        )

    def insert_retention_report(self, report: RetentionReport) -> bool:
        if report.config_hash != self.config.config_hash:
            raise ValueError("retention configuration hash mismatch")
        return self._insert(
            "operations_retention_reports",
            "report_id",
            report.report_id,
            ("as_of", "minimum_retention_days", "deletion_performed", "config_hash"),
            (
                _time(report.as_of),
                report.minimum_retention_days,
                int(report.deletion_performed),
                report.config_hash,
            ),
            report,
        )

    def backup(self, backup_id: str) -> BackupManifest:
        row = self.repository.connection.execute(
            "SELECT payload_json FROM operations_backup_manifests WHERE backup_id = ?",
            (backup_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown backup manifest")
        value = json.loads(str(row[0]))
        return BackupManifest(
            str(value["backup_id"]),
            datetime.fromisoformat(str(value["known_at"]["__datetime__"]).replace("Z", "+00:00")),
            str(value["source_path"]),
            str(value["artifact_path"]),
            str(value["artifact_hash"]),
            int(value["artifact_bytes"]),
            str(value["source_revision"]),
            str(value["code_version"]),
            tuple(str(item) for item in value["quick_check"]),
            int(value["foreign_key_violations"]),
            str(value["config_hash"]),
        )

    def retention_report(self, as_of: datetime) -> RetentionReport:
        cutoff = _time(as_of - timedelta(days=self.config.minimum_retention_days))
        future = self.repository.connection.execute(
            "SELECT backup_id FROM operations_backup_manifests WHERE known_at > ?",
            (_time(as_of),),
        ).fetchall()
        if future:
            raise ValueError("retention report cannot include future backup evidence")
        protected = self.repository.connection.execute(
            """SELECT backup_id FROM operations_backup_manifests
               WHERE known_at > ? ORDER BY backup_id""",
            (cutoff,),
        ).fetchall()
        eligible = self.repository.connection.execute(
            """SELECT backup_id FROM operations_backup_manifests
               WHERE known_at <= ? ORDER BY backup_id""",
            (cutoff,),
        ).fetchall()
        return RetentionReport.create(
            as_of=as_of,
            protected_backup_ids=tuple(str(row[0]) for row in protected),
            review_eligible_backup_ids=tuple(str(row[0]) for row in eligible),
            config=self.config,
        )
