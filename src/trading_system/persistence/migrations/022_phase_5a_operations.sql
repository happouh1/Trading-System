CREATE TABLE IF NOT EXISTS operations_manifests (
    manifest_id TEXT PRIMARY KEY,
    known_at TEXT NOT NULL,
    status TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    code_version TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_component_evidence (
    evidence_id TEXT PRIMARY KEY,
    manifest_id TEXT NOT NULL REFERENCES operations_manifests(manifest_id),
    component TEXT NOT NULL,
    database_label TEXT NOT NULL,
    known_at TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(manifest_id, component)
);

CREATE INDEX IF NOT EXISTS idx_operations_evidence_manifest
    ON operations_component_evidence(manifest_id, component);
