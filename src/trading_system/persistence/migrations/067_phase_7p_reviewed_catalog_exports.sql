CREATE TABLE IF NOT EXISTS reviewed_range_catalog_exports (
    catalog_export_id TEXT PRIMARY KEY,
    catalog_id TEXT NOT NULL REFERENCES reviewed_range_bundle_catalogs(catalog_id),
    output_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count > 0),
    catalog_root TEXT NOT NULL,
    entry_count INTEGER NOT NULL CHECK (entry_count > 0),
    catalog_config_hash TEXT NOT NULL,
    export_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (catalog_id, output_path, content_hash, export_config_hash)
);

CREATE INDEX IF NOT EXISTS idx_reviewed_range_catalog_exports_catalog
ON reviewed_range_catalog_exports(catalog_id, catalog_export_id);
