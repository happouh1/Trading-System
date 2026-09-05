CREATE TABLE IF NOT EXISTS reviewed_range_catalog_export_verifications (
    verification_id TEXT PRIMARY KEY,
    catalog_export_id TEXT NOT NULL REFERENCES reviewed_range_catalog_exports(catalog_export_id),
    catalog_id TEXT NOT NULL REFERENCES reviewed_range_bundle_catalogs(catalog_id),
    verified_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED', 'FAILED')),
    expected_hash TEXT NOT NULL,
    actual_hash TEXT,
    reasons_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    export_config_hash TEXT NOT NULL,
    catalog_config_hash TEXT NOT NULL,
    bundle_config_hash TEXT NOT NULL,
    source_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviewed_range_catalog_export_verifications_source
ON reviewed_range_catalog_export_verifications(catalog_export_id, verified_at, verification_id);
