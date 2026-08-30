"""Causal Phase 5F release-evidence evaluation and persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from trading_system import PACKAGE_VERSION
from trading_system.operations.release_config import OperationsReleaseConfig
from trading_system.operations.release_contracts import ReleaseEvidenceBundle
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("release evidence timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _hash_matches(payload_json: str, payload_hash: str) -> bool:
    try:
        return canonical_hash(json.loads(payload_json)) == payload_hash
    except (json.JSONDecodeError, TypeError):
        return False


class OperationsReleaseRegistry:
    def __init__(self, repository: SQLiteRepository, config: OperationsReleaseConfig) -> None:
        self.repository = repository
        self.config = config

    def _evidence(
        self,
        *,
        table: str,
        id_column: str,
        identity: str,
        time_column: str,
        expected_status: str | None,
        as_of: datetime,
        reasons: list[str],
        hashes: list[tuple[str, str]],
        name: str,
    ) -> tuple[object, ...] | None:
        allowed = {
            ("operations_manifests", "manifest_id", "known_at"),
            ("operations_monitor_reports", "report_id", "as_of"),
        }
        if (table, id_column, time_column) not in allowed:
            raise ValueError("unsupported release evidence source")
        row = self.repository.connection.execute(
            f"""SELECT {time_column}, status, payload_json, payload_hash
                FROM {table} WHERE {id_column} = ?""",
            (identity,),
        ).fetchone()
        if row is None:
            reasons.append(f"{name}_MISSING")
            return None
        known_at = str(row[0])
        status = str(row[1])
        payload_json = str(row[2])
        payload_hash = str(row[3])
        if known_at > _time(as_of):
            reasons.append(f"{name}_FUTURE_EVIDENCE")
        if expected_status is not None and status != expected_status:
            reasons.append(f"{name}_STATUS_{status}")
        if not _hash_matches(payload_json, payload_hash):
            reasons.append(f"{name}_PAYLOAD_HASH_MISMATCH")
        hashes.append((name, payload_hash))
        return tuple(row)

    def evaluate(
        self,
        *,
        as_of: datetime,
        readiness_manifest_id: str,
        monitor_report_id: str,
        control_snapshot_id: str,
        run_request_id: str,
        backup_id: str,
        restore_verification_id: str,
        source_revision: str,
    ) -> ReleaseEvidenceBundle:
        if not source_revision:
            raise ValueError("release evidence source revision is required")
        required = dict(self.config.required_statuses)
        reasons: list[str] = []
        hashes: list[tuple[str, str]] = []
        readiness = self._evidence(
            table="operations_manifests",
            id_column="manifest_id",
            identity=readiness_manifest_id,
            time_column="known_at",
            expected_status=required["readiness_manifest"],
            as_of=as_of,
            reasons=reasons,
            hashes=hashes,
            name="READINESS_MANIFEST",
        )
        self._evidence(
            table="operations_monitor_reports",
            id_column="report_id",
            identity=monitor_report_id,
            time_column="as_of",
            expected_status=required["monitor_report"],
            as_of=as_of,
            reasons=reasons,
            hashes=hashes,
            name="MONITOR_REPORT",
        )
        control = self.repository.connection.execute(
            """SELECT as_of, status, request_id, payload_json, payload_hash
               FROM operations_control_snapshots WHERE snapshot_id = ?""",
            (control_snapshot_id,),
        ).fetchone()
        if control is None:
            reasons.append("CONTROL_SNAPSHOT_MISSING")
        else:
            if str(control[0]) > _time(as_of):
                reasons.append("CONTROL_SNAPSHOT_FUTURE_EVIDENCE")
            if str(control[1]) != required["control_snapshot"]:
                reasons.append(f"CONTROL_SNAPSHOT_STATUS_{control[1]}")
            if str(control[2]) != run_request_id:
                reasons.append("CONTROL_SNAPSHOT_REQUEST_MISMATCH")
            payload_hash = str(control[4])
            if not _hash_matches(str(control[3]), payload_hash):
                reasons.append("CONTROL_SNAPSHOT_PAYLOAD_HASH_MISMATCH")
            hashes.append(("CONTROL_SNAPSHOT", payload_hash))
        attempt = self.repository.connection.execute(
            """SELECT finished_at, status, payload_json, payload_hash
               FROM operations_run_attempts WHERE request_id = ?
               ORDER BY attempt_number DESC LIMIT 1""",
            (run_request_id,),
        ).fetchone()
        if attempt is None:
            reasons.append("RUN_ATTEMPT_MISSING")
        else:
            if str(attempt[0]) > _time(as_of):
                reasons.append("RUN_ATTEMPT_FUTURE_EVIDENCE")
            if str(attempt[1]) != required["run_attempt"]:
                reasons.append(f"RUN_ATTEMPT_STATUS_{attempt[1]}")
            payload_hash = str(attempt[3])
            if not _hash_matches(str(attempt[2]), payload_hash):
                reasons.append("RUN_ATTEMPT_PAYLOAD_HASH_MISMATCH")
            hashes.append(("RUN_ATTEMPT", payload_hash))
        backup = self.repository.connection.execute(
            """SELECT known_at, code_version, payload_json, payload_hash
               FROM operations_backup_manifests WHERE backup_id = ?""",
            (backup_id,),
        ).fetchone()
        if backup is None:
            reasons.append("BACKUP_MANIFEST_MISSING")
        else:
            if str(backup[0]) > _time(as_of):
                reasons.append("BACKUP_MANIFEST_FUTURE_EVIDENCE")
            if str(backup[1]) != PACKAGE_VERSION:
                reasons.append("BACKUP_MANIFEST_CODE_VERSION_MISMATCH")
            payload_hash = str(backup[3])
            if not _hash_matches(str(backup[2]), payload_hash):
                reasons.append("BACKUP_MANIFEST_PAYLOAD_HASH_MISMATCH")
            hashes.append(("BACKUP_MANIFEST", payload_hash))
        restore = self.repository.connection.execute(
            """SELECT known_at, status, backup_id, payload_json, payload_hash
               FROM operations_restore_verifications WHERE verification_id = ?""",
            (restore_verification_id,),
        ).fetchone()
        if restore is None:
            reasons.append("RESTORE_VERIFICATION_MISSING")
        else:
            if str(restore[0]) > _time(as_of):
                reasons.append("RESTORE_VERIFICATION_FUTURE_EVIDENCE")
            if str(restore[1]) != required["restore_verification"]:
                reasons.append(f"RESTORE_VERIFICATION_STATUS_{restore[1]}")
            if str(restore[2]) != backup_id:
                reasons.append("RESTORE_VERIFICATION_BACKUP_MISMATCH")
            payload_hash = str(restore[4])
            if not _hash_matches(str(restore[3]), payload_hash):
                reasons.append("RESTORE_VERIFICATION_PAYLOAD_HASH_MISMATCH")
            hashes.append(("RESTORE_VERIFICATION", payload_hash))
        if readiness is not None:
            code_row = self.repository.connection.execute(
                "SELECT code_version FROM operations_manifests WHERE manifest_id = ?",
                (readiness_manifest_id,),
            ).fetchone()
            if code_row is None or str(code_row[0]) != PACKAGE_VERSION:
                reasons.append("READINESS_MANIFEST_CODE_VERSION_MISMATCH")
        return ReleaseEvidenceBundle.create(
            as_of=as_of,
            readiness_manifest_id=readiness_manifest_id,
            monitor_report_id=monitor_report_id,
            control_snapshot_id=control_snapshot_id,
            run_request_id=run_request_id,
            backup_id=backup_id,
            restore_verification_id=restore_verification_id,
            evidence_hashes=tuple(hashes),
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )

    def insert(self, bundle: ReleaseEvidenceBundle) -> bool:
        if bundle.config_hash != self.config.config_hash:
            raise ValueError("release evidence configuration hash mismatch")
        payload_json = canonical_json(bundle)
        payload_hash = canonical_hash(bundle)
        values = (
            bundle.bundle_id,
            _time(bundle.as_of),
            bundle.status.value,
            bundle.source_revision,
            bundle.code_version,
            bundle.config_hash,
            payload_json,
            payload_hash,
        )
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO operations_release_evidence_bundles
               (bundle_id, as_of, status, source_revision, code_version, config_hash,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            values,
        )
        if cursor.rowcount == 0:
            stored = self.repository.connection.execute(
                """SELECT bundle_id, as_of, status, source_revision, code_version, config_hash,
                          payload_json, payload_hash
                   FROM operations_release_evidence_bundles WHERE bundle_id = ?""",
                (bundle.bundle_id,),
            ).fetchone()
            if stored != values:
                raise ValueError(f"conflicting release evidence bundle: {bundle.bundle_id}")
            return False
        self.repository.connection.commit()
        return True

    def status(self, bundle_id: str) -> tuple[str, str]:
        row = self.repository.connection.execute(
            """SELECT status, payload_json FROM operations_release_evidence_bundles
               WHERE bundle_id = ?""",
            (bundle_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown release evidence bundle")
        return str(row[0]), str(row[1])
