CREATE TABLE IF NOT EXISTS reviewed_range_evidence_bundle_exports (
    reviewed_bundle_export_id TEXT PRIMARY KEY,
    reviewed_bundle_id TEXT NOT NULL,
    source_bundle_id TEXT NOT NULL,
    report_id TEXT NOT NULL REFERENCES range_evaluation_reports(report_id),
    output_path TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_bytes INTEGER NOT NULL CHECK (artifact_bytes > 0),
    review_root TEXT NOT NULL,
    review_count INTEGER NOT NULL CHECK (review_count > 0),
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (reviewed_bundle_id, output_path)
);
CREATE INDEX IF NOT EXISTS idx_reviewed_range_bundles_source
ON reviewed_range_evidence_bundle_exports(source_bundle_id, reviewed_bundle_id);
