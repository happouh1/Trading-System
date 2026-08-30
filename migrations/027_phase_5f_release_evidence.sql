CREATE TABLE IF NOT EXISTS operations_release_evidence_bundles (
    bundle_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_release_bundle_time
    ON operations_release_evidence_bundles(as_of, bundle_id);
