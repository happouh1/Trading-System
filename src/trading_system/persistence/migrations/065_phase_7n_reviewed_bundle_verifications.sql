CREATE TABLE IF NOT EXISTS reviewed_range_bundle_verifications (
    verification_id TEXT PRIMARY KEY,
    reviewed_bundle_export_id TEXT NOT NULL REFERENCES reviewed_range_evidence_bundle_exports(reviewed_bundle_export_id),
    reviewed_bundle_id TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED', 'FAILED')),
    expected_hash TEXT NOT NULL,
    actual_hash TEXT,
    reasons_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    source_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviewed_range_bundle_verifications_export
ON reviewed_range_bundle_verifications(reviewed_bundle_export_id, verified_at, verification_id);
