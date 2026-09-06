"""Append-only persistence for Phase 8C confirmatory evidence reports."""

from __future__ import annotations

import json
from dataclasses import dataclass

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_confirmatory import RangeConfirmatoryConfig
from trading_system.research.range_confirmatory_registry import (
    RangeConfirmatoryAdapterConfig,
    RangeConfirmatoryRegistry,
)
from trading_system.research.range_confirmatory_report import (
    RangeConfirmatoryReport,
    RangeConfirmatoryReportConfig,
    build_range_confirmatory_report,
)
from trading_system.serialization import canonical_hash, canonical_json


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryReportStatus:
    report_id: str
    plan_id: str
    family_size: int
    rejected_null_count: int
    complete: bool
    report_version: str = "8C.1.0"
    production_authority: bool = False


class RangeConfirmatoryReportRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        source_registry: RangeConfirmatoryRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.source_registry = source_registry or RangeConfirmatoryRegistry(repository)

    def materialize(
        self,
        plan_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
    ) -> RangeConfirmatoryReport:
        report = self._build(plan_id, analysis_config, adapter_config, report_config)
        payload_json = canonical_json(report)
        payload_hash = canonical_hash(report)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_confirmatory_reports
               (report_id, plan_id, analysis_config_hash, adapter_config_hash,
                report_config_hash, family_size, rejected_null_count,
                payload_json, payload_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report.report_id, report.plan_id, report.analysis_config_hash,
                report.adapter_config_hash, report.report_config_hash,
                report.family_size, report.rejected_null_count, payload_json, payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                """SELECT plan_id, analysis_config_hash, adapter_config_hash,
                          report_config_hash, payload_hash
                   FROM range_confirmatory_reports WHERE report_id = ?""",
                (report.report_id,),
            ).fetchone()
            expected = (
                report.plan_id, report.analysis_config_hash, report.adapter_config_hash,
                report.report_config_hash, payload_hash,
            )
            if stored != expected:
                raise ValueError(f"conflicting Phase 8C report: {report.report_id}")
        self.repository.connection.commit()
        return report

    def _build(
        self,
        plan_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
    ) -> RangeConfirmatoryReport:
        tests = self.source_registry.load_verified(
            plan_id, analysis_config, adapter_config
        )
        return build_range_confirmatory_report(
            report_config,
            plan_id=plan_id,
            tests=tests,
            analysis_config_hash=analysis_config.config_hash,
            adapter_config_hash=adapter_config.config_hash,
        )

    def status(
        self,
        report_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
    ) -> RangeConfirmatoryReportStatus:
        row = self.repository.connection.execute(
            """SELECT plan_id, analysis_config_hash, adapter_config_hash,
                      report_config_hash, family_size, rejected_null_count,
                      payload_json, payload_hash
               FROM range_confirmatory_reports WHERE report_id = ?""",
            (report_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Phase 8C report does not exist")
        payload = json.loads(str(row[6]))
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[7]):
            raise ValueError("stored Phase 8C report is corrupt")
        plan_id = str(row[0])
        expected = self._build(
            plan_id, analysis_config, adapter_config, report_config
        )
        actual = json.loads(str(row[6]))
        complete = (
            report_id == expected.report_id
            and actual == json.loads(canonical_json(expected))
            and str(row[1]) == expected.analysis_config_hash
            and str(row[2]) == expected.adapter_config_hash
            and str(row[3]) == expected.report_config_hash
            and int(row[4]) == expected.family_size
            and int(row[5]) == expected.rejected_null_count
        )
        return RangeConfirmatoryReportStatus(
            report_id, plan_id, int(row[4]), int(row[5]), complete,
        )

    def load_verified(
        self,
        report_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
    ) -> RangeConfirmatoryReport:
        status = self.status(
            report_id, analysis_config, adapter_config, report_config
        )
        if not status.complete:
            raise ValueError("Phase 8C report is incomplete or has source drift")
        return self._build(
            status.plan_id, analysis_config, adapter_config, report_config
        )
