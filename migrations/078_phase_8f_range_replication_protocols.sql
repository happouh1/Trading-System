CREATE TABLE IF NOT EXISTS range_replication_protocols (
    protocol_id TEXT PRIMARY KEY,
    source_export_id TEXT NOT NULL REFERENCES range_confirmatory_report_exports(export_id),
    source_report_id TEXT NOT NULL REFERENCES range_confirmatory_reports(report_id),
    future_dataset_id TEXT NOT NULL,
    declared_at TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    protocol_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (source_export_id, future_dataset_id, definition_hash, protocol_config_hash)
);

CREATE INDEX IF NOT EXISTS idx_range_replication_protocols_source
ON range_replication_protocols(source_export_id, protocol_id);
