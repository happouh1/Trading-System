"""Append-only Phase 8F prospective replication protocol registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from trading_system.persistence import SQLiteRepository
from trading_system.research.range_confirmatory import RangeConfirmatoryConfig
from trading_system.research.range_confirmatory_export import RangeConfirmatoryExportConfig
from trading_system.research.range_confirmatory_export_registry import (
    RangeConfirmatoryExportRegistry,
)
from trading_system.research.range_confirmatory_registry import (
    RangeConfirmatoryAdapterConfig,
)
from trading_system.research.range_confirmatory_report import (
    RangeConfirmatoryReportConfig,
)
from trading_system.research.range_replication_protocol import (
    RangeReplicationProtocol,
    RangeReplicationProtocolConfig,
    build_range_replication_protocol,
)
from trading_system.serialization import canonical_hash, canonical_json, deterministic_id

_DEFINITION_FIELDS = (
    "capacity_spec",
    "data_freeze_rule",
    "declared_at",
    "dependence_diagnostics_spec",
    "economic_threshold_spec",
    "estimator_spec",
    "future_dataset_id",
    "interval_spec",
    "point_in_time_universe_spec",
    "pooling_spec",
    "protocol_name",
    "replication_acceptance_spec",
    "review_authority_reference",
    "transaction_cost_spec",
)


@dataclass(frozen=True, slots=True)
class RangeReplicationProtocolStatus:
    protocol_id: str
    source_export_id: str
    source_report_id: str
    future_dataset_id: str
    declared_at: str
    definition_hash: str
    complete: bool
    protocol_version: str = "8F.1.0"
    prospective_replication_only: bool = True
    production_authority: bool = False


class RangeReplicationProtocolRegistry:
    def __init__(
        self,
        repository: SQLiteRepository,
        source_registry: RangeConfirmatoryExportRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.source_registry = source_registry or RangeConfirmatoryExportRegistry(repository)

    def register(
        self,
        source_export_id: str,
        manifest: Mapping[str, object],
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
        export_config: RangeConfirmatoryExportConfig,
        protocol_config: RangeReplicationProtocolConfig,
    ) -> RangeReplicationProtocol:
        source = self.source_registry.status(
            source_export_id,
            analysis_config,
            adapter_config,
            report_config,
            export_config,
        )
        protocol = build_range_replication_protocol(
            protocol_config, source=source, manifest=manifest
        )
        payload_json = canonical_json(protocol)
        payload_hash = canonical_hash(protocol)
        cursor = self.repository.connection.execute(
            """INSERT OR IGNORE INTO range_replication_protocols
               (protocol_id, source_export_id, source_report_id, future_dataset_id,
                declared_at, definition_hash, protocol_config_hash, payload_json, payload_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                protocol.protocol_id,
                protocol.source_export_id,
                protocol.source_report_id,
                protocol.future_dataset_id,
                protocol.declared_at,
                protocol.definition_hash,
                protocol.protocol_config_hash,
                payload_json,
                payload_hash,
            ),
        )
        if not cursor.rowcount:
            stored = self.repository.connection.execute(
                """SELECT source_export_id, source_report_id, definition_hash,
                          protocol_config_hash, payload_hash
                   FROM range_replication_protocols WHERE protocol_id = ?""",
                (protocol.protocol_id,),
            ).fetchone()
            expected = (
                protocol.source_export_id,
                protocol.source_report_id,
                protocol.definition_hash,
                protocol.protocol_config_hash,
                payload_hash,
            )
            if stored != expected:
                raise ValueError(f"conflicting Phase 8F protocol: {protocol.protocol_id}")
        self.repository.connection.commit()
        return protocol

    def status(
        self,
        protocol_id: str,
        analysis_config: RangeConfirmatoryConfig,
        adapter_config: RangeConfirmatoryAdapterConfig,
        report_config: RangeConfirmatoryReportConfig,
        export_config: RangeConfirmatoryExportConfig,
        protocol_config: RangeReplicationProtocolConfig,
    ) -> RangeReplicationProtocolStatus:
        row = self.repository.connection.execute(
            """SELECT source_export_id, source_report_id, future_dataset_id, declared_at,
                      definition_hash, protocol_config_hash, payload_json, payload_hash
               FROM range_replication_protocols WHERE protocol_id = ?""",
            (protocol_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Phase 8F protocol does not exist")
        payload = json.loads(str(row[6]))
        if not isinstance(payload, dict) or canonical_hash(payload) != str(row[7]):
            raise ValueError("stored Phase 8F protocol is corrupt")
        for key, expected in (
            ("protocol_id", protocol_id),
            ("source_export_id", row[0]),
            ("source_report_id", row[1]),
            ("future_dataset_id", row[2]),
            ("declared_at", row[3]),
            ("definition_hash", row[4]),
            ("protocol_config_hash", row[5]),
        ):
            if payload.get(key) != expected:
                raise ValueError(f"Phase 8F protocol {key} mismatch")
        if str(row[5]) != protocol_config.config_hash:
            raise ValueError("Phase 8F protocol configuration mismatch")
        source = self.source_registry.status(
            str(row[0]),
            analysis_config,
            adapter_config,
            report_config,
            export_config,
        )
        if source.report_id != str(row[1]) or not source.verified:
            raise ValueError("Phase 8F protocol source is incomplete")
        values = self._definition(payload)
        expected_definition_hash = canonical_hash(values)
        expected_id = deterministic_id(
            "range_replication_protocol",
            (
                source.export_id,
                source.report_id,
                values,
                expected_definition_hash,
                protocol_config.config_hash,
                "8F.1.0",
            ),
        )
        complete = (
            protocol_id == expected_id
            and str(row[4]) == expected_definition_hash
            and payload.get("protocol_version") == "8F.1.0"
            and payload.get("prospective_replication_only") is True
            and payload.get("source_results_already_exist") is True
            and all(
                payload.get(key) is False
                for key in (
                    "analysis_performed",
                    "efficacy_claimed",
                    "parameter_selection_performed",
                    "approval_granted",
                    "network_used",
                    "broker_write_performed",
                    "production_authority",
                )
            )
        )
        return RangeReplicationProtocolStatus(
            protocol_id,
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            complete,
        )

    @staticmethod
    def _definition(payload: Mapping[str, object]) -> dict[str, str]:
        values: dict[str, str] = {}
        for field in _DEFINITION_FIELDS:
            value = payload.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"Phase 8F protocol {field} is invalid")
            values[field] = value
        return values
