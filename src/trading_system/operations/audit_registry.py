"""Phase 6C offline observation-audit packet assembly and persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.audit_config import ObservationAuditConfig
from trading_system.operations.audit_contracts import AuditArtifact, ObservationAuditPacket
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("audit packet timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _root(payload_json: str, payload_hash: str) -> dict[str, Any] | None:
    try:
        value: object = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    if canonical_json(value) != payload_json or canonical_hash(value) != payload_hash:
        return None
    return value


def _artifact(
    name: str, record_id: str, payload_json: str, payload_hash: str
) -> AuditArtifact | None:
    if _root(payload_json, payload_hash) is None:
        return None
    return AuditArtifact(name, record_id, payload_json, payload_hash)


class ObservationAuditRegistry:
    def __init__(self, repository: SQLiteRepository, config: ObservationAuditConfig) -> None:
        self.repository = repository
        self.config = config

    def create(
        self,
        *,
        reconciliation_id: str,
        created_at: datetime,
        source_revision: str,
    ) -> ObservationAuditPacket:
        if not reconciliation_id or not source_revision:
            raise ValueError("audit reconciliation ID and source revision are required")
        row = self.repository.connection.execute(
            """SELECT plan_id, campaign_report_id, reconciled_at, status, campaign_status,
                      code_version, payload_json, payload_hash
               FROM operations_observation_plan_reconciliations
               WHERE reconciliation_id = ?""",
            (reconciliation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation plan reconciliation")
        plan_id = str(row[0])
        campaign_report_id = str(row[1])
        if _time(created_at) < str(row[2]):
            raise ValueError("audit packet cannot predate its reconciliation")

        reasons: list[str] = []
        artifacts: list[AuditArtifact] = []
        reconciliation_root = self._append_artifact(
            artifacts,
            reasons,
            name="OBSERVATION_RECONCILIATION",
            record_id=reconciliation_id,
            payload_json=str(row[6]),
            payload_hash=str(row[7]),
        )
        if str(row[5]) != PACKAGE_VERSION:
            reasons.append("RECONCILIATION_CODE_VERSION_MISMATCH")
        if reconciliation_root is not None:
            if reconciliation_root.get("plan_id") != plan_id:
                reasons.append("RECONCILIATION_PLAN_LINK_MISMATCH")
            if reconciliation_root.get("campaign_report_id") != campaign_report_id:
                reasons.append("RECONCILIATION_CAMPAIGN_LINK_MISMATCH")
            if reconciliation_root.get("code_version") != PACKAGE_VERSION:
                reasons.append("RECONCILIATION_PAYLOAD_CODE_VERSION_MISMATCH")

        plan_hash = self._collect_plan(
            plan_id, reconciliation_root, artifacts, reasons
        )
        campaign_hash = self._collect_campaign(
            campaign_report_id, reconciliation_root, artifacts, reasons
        )
        if reconciliation_root is not None:
            if reconciliation_root.get("plan_hash") != plan_hash:
                reasons.append("RECONCILIATION_PLAN_HASH_MISMATCH")
            if reconciliation_root.get("campaign_hash") != campaign_hash:
                reasons.append("RECONCILIATION_CAMPAIGN_HASH_MISMATCH")

        return ObservationAuditPacket.create(
            plan_id=plan_id,
            reconciliation_id=reconciliation_id,
            campaign_report_id=campaign_report_id,
            created_at=created_at,
            reconciliation_status=str(row[3]),
            campaign_status=str(row[4]),
            artifacts=tuple(artifacts),
            reasons=tuple(reasons),
            source_revision=source_revision,
            config=self.config,
        )

    @staticmethod
    def _append_artifact(
        artifacts: list[AuditArtifact],
        reasons: list[str],
        *,
        name: str,
        record_id: str,
        payload_json: str,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        artifact = _artifact(name, record_id, payload_json, payload_hash)
        if artifact is None:
            reasons.append(f"{name}_PAYLOAD_CORRUPT")
            return None
        artifacts.append(artifact)
        return _root(payload_json, payload_hash)

    def _collect_plan(
        self,
        plan_id: str,
        reconciliation_root: dict[str, Any] | None,
        artifacts: list[AuditArtifact],
        reasons: list[str],
    ) -> str | None:
        row = self.repository.connection.execute(
            """SELECT code_version, payload_json, payload_hash
               FROM operations_observation_plans WHERE plan_id = ?""",
            (plan_id,),
        ).fetchone()
        if row is None:
            reasons.append("OBSERVATION_PLAN_MISSING")
            return None
        payload_hash = str(row[2])
        root = self._append_artifact(
            artifacts,
            reasons,
            name="OBSERVATION_PLAN",
            record_id=plan_id,
            payload_json=str(row[1]),
            payload_hash=payload_hash,
        )
        if str(row[0]) != PACKAGE_VERSION:
            reasons.append("OBSERVATION_PLAN_CODE_VERSION_MISMATCH")
        if root is not None:
            if root.get("plan_id") != plan_id:
                reasons.append("OBSERVATION_PLAN_ID_MISMATCH")
            if root.get("code_version") != PACKAGE_VERSION:
                reasons.append("OBSERVATION_PLAN_PAYLOAD_CODE_VERSION_MISMATCH")
        self._collect_children(
            table="operations_observation_plan_windows",
            parent_column="plan_id",
            parent_id=plan_id,
            id_column="window_id",
            prefix="OBSERVATION_PLAN_WINDOW",
            root=root,
            artifacts=artifacts,
            reasons=reasons,
        )
        if reconciliation_root is not None and reconciliation_root.get("plan_id") != plan_id:
            reasons.append("OBSERVATION_PLAN_RECONCILIATION_LINK_MISMATCH")
        return payload_hash

    def _collect_campaign(
        self,
        report_id: str,
        reconciliation_root: dict[str, Any] | None,
        artifacts: list[AuditArtifact],
        reasons: list[str],
    ) -> str | None:
        row = self.repository.connection.execute(
            """SELECT code_version, payload_json, payload_hash
               FROM operations_shadow_campaign_reports WHERE report_id = ?""",
            (report_id,),
        ).fetchone()
        if row is None:
            reasons.append("SHADOW_CAMPAIGN_REPORT_MISSING")
            return None
        payload_hash = str(row[2])
        root = self._append_artifact(
            artifacts,
            reasons,
            name="SHADOW_CAMPAIGN_REPORT",
            record_id=report_id,
            payload_json=str(row[1]),
            payload_hash=payload_hash,
        )
        if str(row[0]) != PACKAGE_VERSION:
            reasons.append("SHADOW_CAMPAIGN_CODE_VERSION_MISMATCH")
        if root is not None:
            if root.get("report_id") != report_id:
                reasons.append("SHADOW_CAMPAIGN_REPORT_ID_MISMATCH")
            if root.get("code_version") != PACKAGE_VERSION:
                reasons.append("SHADOW_CAMPAIGN_PAYLOAD_CODE_VERSION_MISMATCH")
        self._collect_children(
            table="operations_shadow_campaign_windows",
            parent_column="report_id",
            parent_id=report_id,
            id_column="window_id",
            prefix="SHADOW_CAMPAIGN_WINDOW",
            root=root,
            artifacts=artifacts,
            reasons=reasons,
        )
        if (
            reconciliation_root is not None
            and reconciliation_root.get("campaign_report_id") != report_id
        ):
            reasons.append("SHADOW_CAMPAIGN_RECONCILIATION_LINK_MISMATCH")
        return payload_hash

    def _collect_children(
        self,
        *,
        table: str,
        parent_column: str,
        parent_id: str,
        id_column: str,
        prefix: str,
        root: dict[str, Any] | None,
        artifacts: list[AuditArtifact],
        reasons: list[str],
    ) -> None:
        allowed = {
            ("operations_observation_plan_windows", "plan_id", "window_id"),
            ("operations_shadow_campaign_windows", "report_id", "window_id"),
        }
        if (table, parent_column, id_column) not in allowed:
            raise ValueError("unsupported audit child source")
        rows = self.repository.connection.execute(
            f"""SELECT {id_column}, payload_json, payload_hash FROM {table}
                WHERE {parent_column} = ? ORDER BY {id_column}""",
            (parent_id,),
        ).fetchall()
        raw = None if root is None else root.get("windows")
        raw_items = raw if isinstance(raw, list) else []
        root_by_id = {
            item.get("window_id"): item
            for item in raw_items
            if isinstance(item, dict) and isinstance(item.get("window_id"), str)
        }
        if root is not None and (
            not isinstance(raw, list)
            or len(root_by_id) != len(raw)
            or len(rows) != len(raw)
        ):
            reasons.append(f"{prefix}_COUNT_MISMATCH")
        for row in rows:
            record_id = str(row[0])
            child = self._append_artifact(
                artifacts,
                reasons,
                name=f"{prefix}:{record_id}",
                record_id=record_id,
                payload_json=str(row[1]),
                payload_hash=str(row[2]),
            )
            if root is not None and child is not None and root_by_id.get(record_id) != child:
                reasons.append(f"{prefix}_PARENT_PAYLOAD_MISMATCH")

    def insert(self, packet: ObservationAuditPacket) -> bool:
        if packet.config_hash != self.config.config_hash:
            raise ValueError("observation audit configuration hash mismatch")
        payload_json = canonical_json(packet)
        payload_hash = canonical_hash(packet)
        values = (
            packet.packet_id,
            packet.plan_id,
            packet.reconciliation_id,
            packet.campaign_report_id,
            _time(packet.created_at),
            packet.status.value,
            packet.reconciliation_status,
            packet.campaign_status,
            packet.artifact_root_hash,
            packet.source_revision,
            packet.code_version,
            packet.config_hash,
            payload_json,
            payload_hash,
        )
        connection = self.repository.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO operations_observation_audit_packets
                   (packet_id, plan_id, reconciliation_id, campaign_report_id, created_at,
                    status, reconciliation_status, campaign_status, artifact_root_hash,
                    source_revision, code_version, config_hash, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = connection.execute(
                    """SELECT packet_id, plan_id, reconciliation_id, campaign_report_id,
                              created_at, status, reconciliation_status, campaign_status,
                              artifact_root_hash, source_revision, code_version, config_hash,
                              payload_json, payload_hash
                       FROM operations_observation_audit_packets WHERE packet_id = ?""",
                    (packet.packet_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(f"conflicting observation audit packet: {packet.packet_id}")
                connection.rollback()
                return False
            for artifact in packet.artifacts:
                connection.execute(
                    """INSERT INTO operations_observation_audit_artifacts
                       (packet_id, artifact_name, record_id, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        packet.packet_id,
                        artifact.name,
                        artifact.record_id,
                        artifact.payload_json,
                        artifact.payload_hash,
                    ),
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise

    def status(self, packet_id: str) -> tuple[str, str, int]:
        row = self.repository.connection.execute(
            """SELECT status, payload_json FROM operations_observation_audit_packets
               WHERE packet_id = ?""",
            (packet_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation audit packet")
        count = self.repository.connection.execute(
            """SELECT COUNT(*) FROM operations_observation_audit_artifacts
               WHERE packet_id = ?""",
            (packet_id,),
        ).fetchone()
        return str(row[0]), str(row[1]), 0 if count is None else int(count[0])
