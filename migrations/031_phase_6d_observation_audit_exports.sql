CREATE TABLE IF NOT EXISTS operations_observation_audit_exports (
    export_id TEXT PRIMARY KEY,
    packet_id TEXT NOT NULL REFERENCES operations_observation_audit_packets(packet_id),
    exported_at TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_bytes INTEGER NOT NULL,
    packet_payload_hash TEXT NOT NULL,
    artifact_root_hash TEXT NOT NULL,
    artifact_count INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_observation_audit_export_verifications (
    verification_id TEXT PRIMARY KEY,
    export_id TEXT NOT NULL REFERENCES operations_observation_audit_exports(export_id),
    verified_at TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observation_audit_exports_packet
    ON operations_observation_audit_exports(packet_id, exported_at, export_id);

CREATE INDEX IF NOT EXISTS idx_observation_audit_export_verifications
    ON operations_observation_audit_export_verifications(export_id, verified_at, verification_id);
