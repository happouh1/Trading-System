"""Append-only Phase 6B observation-plan registration and reconciliation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from trading_system import PACKAGE_VERSION
from trading_system.operations.observation_config import ObservationPlanConfig
from trading_system.operations.observation_contracts import (
    ObservationPlan,
    ObservationPlanReconciliation,
    ObservationPlanWindow,
    ReconciliationStatus,
)
from trading_system.persistence import SQLiteRepository
from trading_system.serialization import canonical_hash, canonical_json


def _time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation plan timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _payload(payload_json: str, payload_hash: str) -> dict[str, Any] | None:
    try:
        value: object = json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    if canonical_hash(value) != payload_hash:
        return None
    return value


class ObservationPlanRegistry:
    def __init__(self, repository: SQLiteRepository, config: ObservationPlanConfig) -> None:
        self.repository = repository
        self.config = config

    def create_plan(
        self,
        *,
        campaign_name: str,
        registered_at: datetime,
        start_at: datetime,
        end_at: datetime,
        windows: tuple[ObservationPlanWindow, ...],
        source_revision: str,
    ) -> ObservationPlan:
        if not campaign_name or not source_revision:
            raise ValueError("observation plan name and source revision are required")
        return ObservationPlan.create(
            campaign_name=campaign_name,
            registered_at=registered_at,
            start_at=start_at,
            end_at=end_at,
            windows=windows,
            source_revision=source_revision,
            config=self.config,
        )

    def insert_plan(self, plan: ObservationPlan) -> bool:
        if plan.config_hash != self.config.config_hash:
            raise ValueError("observation plan configuration hash mismatch")
        payload_json = canonical_json(plan)
        payload_hash = canonical_hash(plan)
        values = (
            plan.plan_id,
            plan.campaign_name,
            _time(plan.registered_at),
            _time(plan.start_at),
            _time(plan.end_at),
            plan.status.value,
            plan.source_revision,
            plan.code_version,
            plan.config_hash,
            payload_json,
            payload_hash,
        )
        connection = self.repository.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO operations_observation_plans
                   (plan_id, campaign_name, registered_at, start_at, end_at, status,
                    source_revision, code_version, config_hash, payload_json, payload_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = connection.execute(
                    """SELECT plan_id, campaign_name, registered_at, start_at, end_at,
                              status, source_revision, code_version, config_hash, payload_json,
                              payload_hash FROM operations_observation_plans WHERE plan_id = ?""",
                    (plan.plan_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(f"conflicting observation plan: {plan.plan_id}")
                connection.rollback()
                return False
            for window in plan.windows:
                payload = canonical_json(window)
                connection.execute(
                    """INSERT INTO operations_observation_plan_windows
                       (plan_id, window_id, expected_as_of, payload_json, payload_hash)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        plan.plan_id,
                        window.window_id,
                        _time(window.expected_as_of),
                        payload,
                        canonical_hash(window),
                    ),
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise

    def reconcile(
        self,
        *,
        plan_id: str,
        campaign_report_id: str,
        reconciled_at: datetime,
        source_revision: str,
    ) -> ObservationPlanReconciliation:
        if not plan_id or not campaign_report_id or not source_revision:
            raise ValueError("reconciliation identities and source revision are required")
        plan_row = self.repository.connection.execute(
            """SELECT campaign_name, start_at, end_at, code_version, config_hash,
                      payload_json, payload_hash FROM operations_observation_plans
               WHERE plan_id = ?""",
            (plan_id,),
        ).fetchone()
        if plan_row is None:
            raise ValueError("unknown observation plan")
        plan_hash = str(plan_row[6])
        plan_root = _payload(str(plan_row[5]), plan_hash)
        if plan_root is None:
            raise ValueError("stored observation plan payload is corrupt")
        if str(plan_row[3]) != PACKAGE_VERSION or plan_root.get("code_version") != PACKAGE_VERSION:
            raise ValueError("stored observation plan code version mismatch")
        if str(plan_row[4]) != self.config.config_hash:
            raise ValueError("stored observation plan configuration hash mismatch")
        plan_windows = self._plan_windows(plan_id, plan_root)

        report_row = self.repository.connection.execute(
            """SELECT campaign_name, start_at, end_at, evaluated_at, status, code_version,
                      payload_json, payload_hash FROM operations_shadow_campaign_reports
               WHERE report_id = ?""",
            (campaign_report_id,),
        ).fetchone()
        if report_row is None:
            return ObservationPlanReconciliation.create(
                plan_id=plan_id,
                campaign_report_id=campaign_report_id,
                reconciled_at=reconciled_at,
                status=ReconciliationStatus.MISSING,
                campaign_status="MISSING",
                reasons=("CAMPAIGN_REPORT_MISSING",),
                plan_hash=plan_hash,
                campaign_hash=None,
                source_revision=source_revision,
                config=self.config,
            )

        campaign_hash = str(report_row[7])
        report_root = _payload(str(report_row[6]), campaign_hash)
        if report_root is None:
            return ObservationPlanReconciliation.create(
                plan_id=plan_id,
                campaign_report_id=campaign_report_id,
                reconciled_at=reconciled_at,
                status=ReconciliationStatus.CORRUPT,
                campaign_status=str(report_row[4]),
                reasons=("CAMPAIGN_REPORT_PAYLOAD_CORRUPT",),
                plan_hash=plan_hash,
                campaign_hash=campaign_hash,
                source_revision=source_revision,
                config=self.config,
            )

        reasons: list[str] = []
        if str(report_row[0]) != str(plan_row[0]):
            reasons.append("CAMPAIGN_NAME_DEVIATION")
        if str(report_row[1]) != str(plan_row[1]) or str(report_row[2]) != str(plan_row[2]):
            reasons.append("CAMPAIGN_BOUNDS_DEVIATION")
        if str(report_row[3]) > _time(reconciled_at):
            reasons.append("CAMPAIGN_REPORT_FUTURE_EVIDENCE")
        if (
            str(report_row[5]) != PACKAGE_VERSION
            or report_root.get("code_version") != PACKAGE_VERSION
        ):
            reasons.append("CAMPAIGN_REPORT_CODE_VERSION_MISMATCH")
        if report_root.get("report_id") != campaign_report_id:
            reasons.append("CAMPAIGN_REPORT_ID_MISMATCH")
        campaign_windows, window_reasons = self._campaign_windows(
            campaign_report_id, report_root
        )
        reasons.extend(window_reasons)
        if campaign_windows != plan_windows:
            plan_ids = {item[0] for item in plan_windows}
            campaign_ids = {item[0] for item in campaign_windows}
            if plan_ids - campaign_ids:
                reasons.append("PREREGISTERED_WINDOWS_OMITTED")
            if campaign_ids - plan_ids:
                reasons.append("UNREGISTERED_WINDOWS_ADDED")
            if plan_ids == campaign_ids:
                reasons.append("PREREGISTERED_WINDOW_TIMESTAMPS_CHANGED")
        status = ReconciliationStatus.MATCHED if not reasons else ReconciliationStatus.DEVIATION
        return ObservationPlanReconciliation.create(
            plan_id=plan_id,
            campaign_report_id=campaign_report_id,
            reconciled_at=reconciled_at,
            status=status,
            campaign_status=str(report_row[4]),
            reasons=tuple(reasons),
            plan_hash=plan_hash,
            campaign_hash=campaign_hash,
            source_revision=source_revision,
            config=self.config,
        )

    def _plan_windows(
        self, plan_id: str, root: dict[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        rows = self.repository.connection.execute(
            """SELECT window_id, expected_as_of, payload_json, payload_hash
               FROM operations_observation_plan_windows WHERE plan_id = ?
               ORDER BY expected_as_of, window_id""",
            (plan_id,),
        ).fetchall()
        raw_windows = root.get("windows")
        if not isinstance(raw_windows, list) or len(raw_windows) != len(rows):
            raise ValueError("stored observation plan windows are corrupt")
        root_by_id = {
            item.get("window_id"): item
            for item in raw_windows
            if isinstance(item, dict) and isinstance(item.get("window_id"), str)
        }
        result: list[tuple[str, str]] = []
        for row in rows:
            child = _payload(str(row[2]), str(row[3]))
            if child is None or root_by_id.get(str(row[0])) != child:
                raise ValueError("stored observation plan window payload is corrupt")
            result.append((str(row[0]), str(row[1])))
        if len(root_by_id) != len(rows):
            raise ValueError("stored observation plan windows are corrupt")
        return tuple(result)

    def _campaign_windows(
        self, report_id: str, root: dict[str, Any]
    ) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
        rows = self.repository.connection.execute(
            """SELECT window_id, expected_as_of, payload_json, payload_hash
               FROM operations_shadow_campaign_windows WHERE report_id = ?
               ORDER BY expected_as_of, window_id""",
            (report_id,),
        ).fetchall()
        reasons: list[str] = []
        raw_windows = root.get("windows")
        if not isinstance(raw_windows, list):
            return (), ("CAMPAIGN_REPORT_WINDOWS_INVALID",)
        root_by_id = {
            item.get("window_id"): item
            for item in raw_windows
            if isinstance(item, dict) and isinstance(item.get("window_id"), str)
        }
        if len(root_by_id) != len(raw_windows) or len(rows) != len(raw_windows):
            reasons.append("CAMPAIGN_REPORT_WINDOW_COUNT_MISMATCH")
        result: list[tuple[str, str]] = []
        for row in rows:
            child = _payload(str(row[2]), str(row[3]))
            if child is None:
                reasons.append("CAMPAIGN_WINDOW_PAYLOAD_CORRUPT")
            elif root_by_id.get(str(row[0])) != child:
                reasons.append("CAMPAIGN_REPORT_WINDOW_PAYLOAD_MISMATCH")
            result.append((str(row[0]), str(row[1])))
        return tuple(result), tuple(sorted(set(reasons)))

    def insert_reconciliation(self, value: ObservationPlanReconciliation) -> bool:
        if value.config_hash != self.config.config_hash:
            raise ValueError("observation reconciliation configuration hash mismatch")
        payload_json = canonical_json(value)
        payload_hash = canonical_hash(value)
        values = (
            value.reconciliation_id,
            value.plan_id,
            value.campaign_report_id,
            _time(value.reconciled_at),
            value.status.value,
            value.campaign_status,
            value.source_revision,
            value.code_version,
            value.config_hash,
            payload_json,
            payload_hash,
        )
        connection = self.repository.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO operations_observation_plan_reconciliations
                   (reconciliation_id, plan_id, campaign_report_id, reconciled_at, status,
                    campaign_status, source_revision, code_version, config_hash, payload_json,
                    payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            if cursor.rowcount == 0:
                stored = connection.execute(
                    """SELECT reconciliation_id, plan_id, campaign_report_id, reconciled_at,
                              status, campaign_status, source_revision, code_version, config_hash,
                              payload_json, payload_hash
                       FROM operations_observation_plan_reconciliations
                       WHERE reconciliation_id = ?""",
                    (value.reconciliation_id,),
                ).fetchone()
                if stored != values:
                    raise ValueError(
                        f"conflicting observation reconciliation: {value.reconciliation_id}"
                    )
                connection.rollback()
                return False
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise

    def plan_status(self, plan_id: str) -> tuple[str, str, int]:
        row = self.repository.connection.execute(
            "SELECT status, payload_json FROM operations_observation_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation plan")
        count = self.repository.connection.execute(
            "SELECT COUNT(*) FROM operations_observation_plan_windows WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        return str(row[0]), str(row[1]), 0 if count is None else int(count[0])

    def reconciliation_status(self, reconciliation_id: str) -> tuple[str, str]:
        row = self.repository.connection.execute(
            """SELECT status, payload_json FROM operations_observation_plan_reconciliations
               WHERE reconciliation_id = ?""",
            (reconciliation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown observation plan reconciliation")
        return str(row[0]), str(row[1])
