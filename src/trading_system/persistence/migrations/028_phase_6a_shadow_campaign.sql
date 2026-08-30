CREATE TABLE IF NOT EXISTS operations_shadow_campaign_reports (
    report_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_shadow_campaign_windows (
    report_id TEXT NOT NULL REFERENCES operations_shadow_campaign_reports(report_id),
    window_id TEXT NOT NULL,
    expected_as_of TEXT NOT NULL,
    bundle_id TEXT,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (report_id, window_id),
    UNIQUE (report_id, expected_as_of)
);

CREATE INDEX IF NOT EXISTS idx_shadow_campaign_reports_time
    ON operations_shadow_campaign_reports(evaluated_at, report_id);

CREATE INDEX IF NOT EXISTS idx_shadow_campaign_windows_bundle
    ON operations_shadow_campaign_windows(bundle_id, report_id, window_id);
