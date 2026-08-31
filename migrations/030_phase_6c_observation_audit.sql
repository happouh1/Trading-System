CREATE TABLE IF NOT EXISTS operations_observation_audit_packets (
    packet_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES operations_observation_plans(plan_id),
    reconciliation_id TEXT NOT NULL REFERENCES operations_observation_plan_reconciliations(reconciliation_id),
    campaign_report_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    reconciliation_status TEXT NOT NULL,
    campaign_status TEXT NOT NULL,
    artifact_root_hash TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_observation_audit_artifacts (
    packet_id TEXT NOT NULL REFERENCES operations_observation_audit_packets(packet_id),
    artifact_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (packet_id, artifact_name)
);

CREATE INDEX IF NOT EXISTS idx_observation_audit_packets_time
    ON operations_observation_audit_packets(created_at, packet_id);

CREATE INDEX IF NOT EXISTS idx_observation_audit_packets_reconciliation
    ON operations_observation_audit_packets(reconciliation_id, packet_id);
