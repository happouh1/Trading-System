CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_bundles (
    bundle_id TEXT PRIMARY KEY,
    export_id TEXT NOT NULL REFERENCES operations_prospective_chain_exports(export_id),
    source_verification_id TEXT NOT NULL REFERENCES operations_prospective_chain_export_verifications(verification_id),
    bundled_at TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_bytes INTEGER NOT NULL,
    export_manifest_hash TEXT NOT NULL,
    source_verification_hash TEXT NOT NULL,
    chain_root_hash TEXT NOT NULL,
    review_root_hash TEXT NOT NULL,
    review_count INTEGER NOT NULL,
    active_review_count INTEGER NOT NULL,
    summary_eligible_count INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_bundle_verifications (
    verification_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL REFERENCES operations_prospective_chain_review_bundles(bundle_id),
    verified_at TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prospective_chain_review_bundles_export
    ON operations_prospective_chain_review_bundles(export_id, bundled_at, bundle_id);

CREATE INDEX IF NOT EXISTS idx_prospective_chain_review_bundle_verifications
    ON operations_prospective_chain_review_bundle_verifications(
        bundle_id, verified_at, verification_id
    );
