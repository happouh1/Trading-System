"""Causal Phase 6A shadow-campaign evaluation and persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.campaign_config import OperationsCampaignConfig
from trading_system.operations.campaign_contracts import (
    CampaignWindow,
    CampaignWindowRequest,
    ShadowCampaignReport,
    WindowStatus,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("campaign timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _object(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return value


def _payload(payload_json: str, payload_hash: str) -> dict[str, Any] | None:
    try:
        value: object = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return None
    root = _object(value)
    if root is None or canonical_hash(root) != payload_hash:
        return None
    return root


class OperationsCampaignRegistry:
    def __init__(self, repository: SQLiteRepository, config: OperationsCampaignConfig) -> None:
        self.repository = repository
        self.config = config

    def evaluate(
        self,
        *,
        campaign_name: str,
        start_at: datetime,
        end_at: datetime,
        evaluated_at: datetime,
        requests: tuple[CampaignWindowRequest, ...],
        source_revision: str,
    ) -> ShadowCampaignReport:
        if not campaign_name or not source_revision:
            raise ValueError("campaign name and source revision are required")
        if not requests:
            raise ValueError("shadow campaign requires at least one declared window")
        canonical = tuple(sorted(requests, key=lambda item: (item.expected_as_of, item.window_id)))
        if len({item.window_id for item in canonical}) != len(canonical):
            raise ValueError("campaign window IDs must be unique")
        if len({item.expected_as_of for item in canonical}) != len(canonical):
            raise ValueError("campaign window timestamps must be unique")
        if start_at > end_at or end_at > evaluated_at:
            raise ValueError("shadow campaign timestamps are inconsistent")
        if any(not start_at <= item.expected_as_of <= end_at for item in canonical):
            raise ValueError("campaign window is outside campaign bounds")
        windows = tuple(self._window(item, evaluated_at) for item in canonical)
        return ShadowCampaignReport.create(
            campaign_name=campaign_name,
            start_at=start_at,
            end_at=end_at,
            evaluated_at=evaluated_at,
            windows=windows,
            source_revision=source_revision,
            config=self.config,
        )

    def _window(
        self, request: CampaignWindowRequest, evaluated_at: datetime
    ) -> CampaignWindow:
        if request.bundle_id is None:
            return CampaignWindow.create(
                window_id=request.window_id,
                expected_as_of=request.expected_as_of,
                bundle_id=None,
                status=WindowStatus.MISSING,
                monitor_status="MISSING",
                run_attempt_status="MISSING",
                control_status="MISSING",
                restore_status="MISSING",
                reasons=("RELEASE_BUNDLE_NOT_DECLARED",),
                evidence_hashes=(),
            )
        row = self.repository.connection.execute(
            """SELECT as_of, status, code_version, payload_json, payload_hash
               FROM operations_release_evidence_bundles WHERE bundle_id = ?""",
            (request.bundle_id,),
        ).fetchone()
        if row is None:
            return CampaignWindow.create(
                window_id=request.window_id,
                expected_as_of=request.expected_as_of,
                bundle_id=request.bundle_id,
                status=WindowStatus.MISSING,
                monitor_status="MISSING",
                run_attempt_status="MISSING",
                control_status="MISSING",
                restore_status="MISSING",
                reasons=("RELEASE_BUNDLE_MISSING",),
                evidence_hashes=(),
            )
        payload_hash = str(row[4])
        root = _payload(str(row[3]), payload_hash)
        if root is None:
            return CampaignWindow.create(
                window_id=request.window_id,
                expected_as_of=request.expected_as_of,
                bundle_id=request.bundle_id,
                status=WindowStatus.CORRUPT,
                monitor_status="UNKNOWN",
                run_attempt_status="UNKNOWN",
                control_status="UNKNOWN",
                restore_status="UNKNOWN",
                reasons=("RELEASE_BUNDLE_PAYLOAD_CORRUPT",),
                evidence_hashes=(("RELEASE_BUNDLE", payload_hash),),
            )
        reasons: list[str] = []
        if str(row[0]) != _time(request.expected_as_of):
            reasons.append("RELEASE_BUNDLE_WINDOW_TIMESTAMP_MISMATCH")
        if str(row[0]) > _time(evaluated_at):
            reasons.append("RELEASE_BUNDLE_FUTURE_EVIDENCE")
        if str(row[1]) != "COMPLETE" or root.get("status") != "COMPLETE":
            reasons.append("RELEASE_BUNDLE_NOT_COMPLETE")
        if root.get("reasons") != []:
            reasons.append("RELEASE_BUNDLE_REASONS_NOT_EMPTY")
        if str(row[2]) != PACKAGE_VERSION or root.get("code_version") != PACKAGE_VERSION:
            reasons.append("RELEASE_BUNDLE_CODE_VERSION_MISMATCH")
        if root.get("bundle_id") != request.bundle_id:
            reasons.append("RELEASE_BUNDLE_ID_MISMATCH")
        required_disclosures = {
            "FRESHNESS_NOT_ASSESSED",
            "NO_BROKER_OR_LIVE_TRADING_AUTHORITY",
            "NOT_A_PRODUCTION_READINESS_CLAIM",
            "OFFLINE_PERSISTED_EVIDENCE_ONLY",
        }
        disclosures = root.get("disclosures")
        if not isinstance(disclosures, list) or set(disclosures) != required_disclosures:
            reasons.append("RELEASE_BUNDLE_DISCLOSURES_INVALID")
        evidence_hashes = self._release_hashes(root, reasons)
        source = self._source_evidence(root, evidence_hashes, reasons)
        status = WindowStatus.COMPLETE if not reasons else WindowStatus.INCOMPLETE
        return CampaignWindow.create(
            window_id=request.window_id,
            expected_as_of=request.expected_as_of,
            bundle_id=request.bundle_id,
            status=status,
            monitor_status=source[0],
            run_attempt_status=source[1],
            control_status=source[2],
            restore_status=source[3],
            reasons=tuple(reasons),
            evidence_hashes=(("RELEASE_BUNDLE", payload_hash), *evidence_hashes),
        )

    @staticmethod
    def _release_hashes(
        root: dict[str, Any], reasons: list[str]
    ) -> tuple[tuple[str, str], ...]:
        raw = root.get("evidence_hashes")
        if not isinstance(raw, list):
            reasons.append("RELEASE_EVIDENCE_HASHES_INVALID")
            return ()
        values: list[tuple[str, str]] = []
        for item in raw:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not all(isinstance(value, str) and value for value in item)
            ):
                reasons.append("RELEASE_EVIDENCE_HASHES_INVALID")
                return ()
            values.append((item[0], item[1]))
        canonical = tuple(sorted(set(values)))
        expected_names = {
            "BACKUP_MANIFEST",
            "CONTROL_SNAPSHOT",
            "MONITOR_REPORT",
            "READINESS_MANIFEST",
            "RESTORE_VERIFICATION",
            "RUN_ATTEMPT",
        }
        if {name for name, _ in canonical} != expected_names:
            reasons.append("RELEASE_EVIDENCE_HASHES_INCOMPLETE")
        return canonical

    def _source_evidence(
        self,
        root: dict[str, Any],
        release_hashes: tuple[tuple[str, str], ...],
        reasons: list[str],
    ) -> tuple[str, str, str, str]:
        hashes = dict(release_hashes)
        readiness = self._source_row(
            "READINESS_MANIFEST",
            "operations_manifests",
            "manifest_id",
            root.get("readiness_manifest_id"),
            "READY",
            hashes,
            reasons,
            require_code=True,
        )
        monitor = self._source_row(
            "MONITOR_REPORT",
            "operations_monitor_reports",
            "report_id",
            root.get("monitor_report_id"),
            "READY",
            hashes,
            reasons,
        )
        control = self._source_row(
            "CONTROL_SNAPSHOT",
            "operations_control_snapshots",
            "snapshot_id",
            root.get("control_snapshot_id"),
            "READY",
            hashes,
            reasons,
        )
        backup = self._source_row(
            "BACKUP_MANIFEST",
            "operations_backup_manifests",
            "backup_id",
            root.get("backup_id"),
            None,
            hashes,
            reasons,
            require_code=True,
        )
        restore = self._source_row(
            "RESTORE_VERIFICATION",
            "operations_restore_verifications",
            "verification_id",
            root.get("restore_verification_id"),
            "VERIFIED",
            hashes,
            reasons,
        )
        request_id = root.get("run_request_id")
        control_link = self.repository.connection.execute(
            "SELECT request_id FROM operations_control_snapshots WHERE snapshot_id = ?",
            (root.get("control_snapshot_id"),),
        ).fetchone()
        if control_link is not None and str(control_link[0]) != request_id:
            reasons.append("CONTROL_SNAPSHOT_SOURCE_REQUEST_MISMATCH")
        restore_link = self.repository.connection.execute(
            "SELECT backup_id FROM operations_restore_verifications WHERE verification_id = ?",
            (root.get("restore_verification_id"),),
        ).fetchone()
        if restore_link is not None and str(restore_link[0]) != root.get("backup_id"):
            reasons.append("RESTORE_VERIFICATION_SOURCE_BACKUP_MISMATCH")
        if not isinstance(request_id, str) or not request_id:
            reasons.append("RUN_ATTEMPT_SOURCE_ID_INVALID")
            attempt = "MISSING"
        else:
            row = self.repository.connection.execute(
                """SELECT status, payload_json, payload_hash FROM operations_run_attempts
                   WHERE request_id = ? ORDER BY attempt_number DESC LIMIT 1""",
                (request_id,),
            ).fetchone()
            if row is None:
                reasons.append("RUN_ATTEMPT_SOURCE_MISSING")
                attempt = "MISSING"
            else:
                attempt = str(row[0])
                if attempt != "SUCCEEDED":
                    reasons.append(f"RUN_ATTEMPT_SOURCE_STATUS_{attempt}")
                if _payload(str(row[1]), str(row[2])) is None:
                    reasons.append("RUN_ATTEMPT_SOURCE_PAYLOAD_CORRUPT")
                if hashes.get("RUN_ATTEMPT") != str(row[2]):
                    reasons.append("RUN_ATTEMPT_SOURCE_HASH_MISMATCH")
        _ = readiness, backup
        return monitor, attempt, control, restore

    def _source_row(
        self,
        name: str,
        table: str,
        id_column: str,
        identity: object,
        expected_status: str | None,
        hashes: dict[str, str],
        reasons: list[str],
        *,
        require_code: bool = False,
    ) -> str:
        allowed = {
            ("operations_manifests", "manifest_id"),
            ("operations_monitor_reports", "report_id"),
            ("operations_control_snapshots", "snapshot_id"),
            ("operations_backup_manifests", "backup_id"),
            ("operations_restore_verifications", "verification_id"),
        }
        if (table, id_column) not in allowed:
            raise ValueError("unsupported campaign evidence source")
        if not isinstance(identity, str) or not identity:
            reasons.append(f"{name}_SOURCE_ID_INVALID")
            return "MISSING"
        code_select = ", code_version" if require_code else ""
        row = self.repository.connection.execute(
            f"SELECT payload_json, payload_hash{code_select} FROM {table} WHERE {id_column} = ?",
            (identity,),
        ).fetchone()
        if row is None:
            reasons.append(f"{name}_SOURCE_MISSING")
            return "MISSING"
        if _payload(str(row[0]), str(row[1])) is None:
            reasons.append(f"{name}_SOURCE_PAYLOAD_CORRUPT")
        if hashes.get(name) != str(row[1]):
            reasons.append(f"{name}_SOURCE_HASH_MISMATCH")
        if require_code and str(row[2]) != PACKAGE_VERSION:
            reasons.append(f"{name}_SOURCE_CODE_VERSION_MISMATCH")
        if expected_status is None:
            return "PRESENT"
        status_row = self.repository.connection.execute(
            f"SELECT status FROM {table} WHERE {id_column} = ?", (identity,)
        ).fetchone()
        status = "MISSING" if status_row is None else str(status_row[0])
        if status != expected_status:
            reasons.append(f"{name}_SOURCE_STATUS_{status}")
        return status

    def insert(self, report: ShadowCampaignReport) -> bool:
        if report.config_hash != self.config.config_hash:
            raise ValueError("shadow campaign configuration hash mismatch")
        payload_json = canonical_json(report)
        payload_hash = canonical_hash(report)
        values = (
            report.report_id,
            report.campaign_name,
            _time(report.start_at),
            _time(report.end_at),
            _time(report.evaluated_at),
            report.status.value,
            report.source_revision,
            report.code_version,
            report.config_hash,
            payload_json,
            payload_hash,
        )
        connection = self.repository.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO operations_shadow_campaign_reports
                   (report_id, campaign_name, start_at, end_at, evaluated_at, status,
                    source_revision, code_version, config_hash, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = connection.execute(
                    """SELECT report_id, campaign_name, start_at, end_at, evaluated_at, status,
                              source_revision, code_version, config_hash, payload_json, payload_hash
                       FROM operations_shadow_campaign_reports WHERE report_id = ?""",
                    (report.report_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(f"conflicting shadow campaign report: {report.report_id}")
                connection.rollback()
                return False
            for window in report.windows:
                window_json = canonical_json(window)
                connection.execute(
                    """INSERT INTO operations_shadow_campaign_windows
                       (report_id, window_id, expected_as_of, bundle_id, status, payload_json,
                        payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        report.report_id,
                        window.window_id,
                        _time(window.expected_as_of),
                        window.bundle_id,
                        window.status.value,
                        window_json,
                        canonical_hash(window),
                    ),
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise

    def status(self, report_id: str) -> tuple[str, str, int]:
        row = self.repository.connection.execute(
            """SELECT status, payload_json FROM operations_shadow_campaign_reports
               WHERE report_id = ?""",
            (report_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown shadow campaign report")
        count = self.repository.connection.execute(
            "SELECT COUNT(*) FROM operations_shadow_campaign_windows WHERE report_id = ?",
            (report_id,),
        ).fetchone()
        return str(row[0]), str(row[1]), 0 if count is None else int(count[0])
