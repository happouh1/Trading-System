CREATE TABLE IF NOT EXISTS range_confirmatory_report_exports (
    export_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES range_confirmatory_reports(report_id),
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    output_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    export_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (report_id, output_path, export_config_hash)
);

CREATE INDEX IF NOT EXISTS idx_range_confirmatory_report_exports_report
ON range_confirmatory_report_exports(report_id, export_id);
