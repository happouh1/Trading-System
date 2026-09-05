CREATE TABLE IF NOT EXISTS reviewed_range_bundle_catalogs (
    catalog_id TEXT PRIMARY KEY, catalog_name TEXT NOT NULL, cataloged_at TEXT NOT NULL,
    catalog_root TEXT NOT NULL, entry_count INTEGER NOT NULL CHECK (entry_count > 0),
    source_revision TEXT NOT NULL, config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviewed_range_bundle_catalog_entries (
    catalog_id TEXT NOT NULL REFERENCES reviewed_range_bundle_catalogs(catalog_id),
    reviewed_bundle_export_id TEXT NOT NULL REFERENCES reviewed_range_evidence_bundle_exports(reviewed_bundle_export_id),
    verification_id TEXT NOT NULL REFERENCES reviewed_range_bundle_verifications(verification_id),
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    PRIMARY KEY (catalog_id, reviewed_bundle_export_id)
);
CREATE INDEX IF NOT EXISTS idx_reviewed_range_bundle_catalogs_name
ON reviewed_range_bundle_catalogs(catalog_name, cataloged_at, catalog_id);
