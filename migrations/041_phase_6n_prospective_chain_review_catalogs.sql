CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_catalogs (
    catalog_id TEXT PRIMARY KEY,
    catalog_name TEXT NOT NULL,
    cataloged_at TEXT NOT NULL,
    catalog_root_hash TEXT NOT NULL,
    bundle_count INTEGER NOT NULL,
    total_review_count INTEGER NOT NULL,
    total_active_review_count INTEGER NOT NULL,
    total_summary_eligible_count INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_catalog_entries (
    catalog_id TEXT NOT NULL REFERENCES operations_prospective_chain_review_catalogs(catalog_id),
    bundle_id TEXT NOT NULL REFERENCES operations_prospective_chain_review_bundles(bundle_id),
    verification_id TEXT NOT NULL REFERENCES operations_prospective_chain_review_bundle_verifications(verification_id),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (catalog_id, bundle_id)
);

CREATE INDEX IF NOT EXISTS idx_prospective_chain_review_catalogs_name
    ON operations_prospective_chain_review_catalogs(catalog_name, cataloged_at, catalog_id);
