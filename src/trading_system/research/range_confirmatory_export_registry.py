"""Append-only receipts and exact-byte verification for Phase 8D exports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_confirmatory import RangeConfirmatoryConfig
from trading_system.research.range_confirmatory_export import (
    RangeConfirmatoryExport,
    RangeConfirmatoryExportConfig,
    render_range_confirmatory_markdown,
    write_range_confirmatory_export,
)
from trading_system.research.range_confirmatory_registry import (
    RangeConfirmatoryAdapterConfig,
)
from trading_system.research.range_confirmatory_report import (
    RangeConfirmatoryReportConfig,
)
from trading_system.research.range_confirmatory_report_registry import (
    RangeConfirmatoryReportRegistry,
)
from trading_system.serialization import canonical_hash, canonical_json


@dataclass(frozen=True, slots=True)
class RangeConfirmatoryExportStatus:
    export_id: str
    report_id: str
    output_path: str
    content_hash: str
    byte_count: int
    verified: bool
    export_version: str = "8D.1.0"
    production_authority: bool = False


class RangeConfirmatoryExportRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        report_registry: RangeConfirmatoryReportRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.report_registry = report_registry or RangeConfirmatoryReportRegistry(repository)

    def export(
        self,
        report_id: str,
        output: str | Path,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
        export_config: RangeConfirmatoryExportConfig,
    ) -> RangeConfirmatoryExport:
        report = self.report_registry.load_verified(
            report_id, analysis_config, adapter_config, report_config
        )
        receipt = write_range_confirmatory_export(
            report, output=output, config=export_config
        )
        payload_json = canonical_json(receipt)
        payload_hash = canonical_hash(receipt)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_confirmatory_report_exports
               (export_id, report_id, plan_id, output_path, content_hash, byte_count,
                export_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.export_id, receipt.report_id, receipt.plan_id,
                receipt.output_path, receipt.content_hash, receipt.byte_count,
                receipt.export_config_hash, payload_json, payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                """SELECT report_id, output_path, content_hash, export_config_hash, payload_hash
                   FROM range_confirmatory_report_exports WHERE export_id = ?""",
                (receipt.export_id,),
            ).fetchone()
            expected = (
                receipt.report_id, receipt.output_path, receipt.content_hash,
                receipt.export_config_hash, payload_hash,
            )
            if stored != expected:
                raise ValueError(f"conflicting Phase 8D export: {receipt.export_id}")
        self.repository.connection.commit()
        return receipt

    def status(
        self,
        export_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
        export_config: RangeConfirmatoryExportConfig,
    ) -> RangeConfirmatoryExportStatus:
        row = self.repository.connection.execute(
            """SELECT report_id, plan_id, output_path, content_hash, byte_count,
                      export_config_hash, payload_json, payload_hash
               FROM range_confirmatory_report_exports WHERE export_id = ?""",
            (export_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Phase 8D export does not exist")
        payload = json.loads(str(row[6]))
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[7]):
            raise ValueError("stored Phase 8D export receipt is corrupt")
        for key, expected in (
            ("export_id", export_id), ("report_id", row[0]), ("plan_id", row[1]),
            ("output_path", row[2]), ("content_hash", row[3]), ("byte_count", row[4]),
            ("export_config_hash", row[5]),
        ):
            if payload.get(key) != expected:
                raise ValueError(f"Phase 8D receipt {key} mismatch")
        if str(row[5]) != export_config.config_hash:
            raise ValueError("Phase 8D export configuration mismatch")
        report = self.report_registry.load_verified(
            str(row[0]), analysis_config, adapter_config, report_config
        )
        expected_content = render_range_confirmatory_markdown(report)
        path = Path(str(row[2]))
        if not path.is_file():
            raise ValueError("Phase 8D export file is missing")
        actual_content = path.read_bytes()
        actual_hash = f"sha256:{hashlib.sha256(actual_content).hexdigest()}"
        verified = (
            actual_content == expected_content
            and actual_hash == str(row[3])
            and len(actual_content) == int(row[4])
        )
        if not verified:
            raise ValueError("Phase 8D export content is corrupt")
        return RangeConfirmatoryExportStatus(
            export_id, str(row[0]), str(row[2]), actual_hash, len(actual_content), True,
        )
