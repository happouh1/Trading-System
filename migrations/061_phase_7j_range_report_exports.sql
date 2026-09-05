CREATE TABLE IF NOT EXISTS range_evaluation_report_exports (
    export_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES range_evaluation_reports(report_id),
    output_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (report_id, output_path, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_range_evaluation_report_exports_report
ON range_evaluation_report_exports(report_id, export_id);
