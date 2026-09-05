CREATE TABLE IF NOT EXISTS range_evaluation_bundle_exports (
    bundle_export_id TEXT PRIMARY KEY,
    bundle_id TEXT NOT NULL,
    report_id TEXT NOT NULL REFERENCES range_evaluation_reports(report_id),
    output_path TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_bytes INTEGER NOT NULL CHECK (artifact_bytes >= 0),
    manifest_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (bundle_id, output_path)
);

CREATE INDEX IF NOT EXISTS idx_range_evaluation_bundle_exports_report
ON range_evaluation_bundle_exports(report_id, bundle_id);
