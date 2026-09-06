CREATE TABLE IF NOT EXISTS range_confirmatory_reports (
    report_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    analysis_config_hash TEXT NOT NULL,
    adapter_config_hash TEXT NOT NULL,
    report_config_hash TEXT NOT NULL,
    family_size INTEGER NOT NULL CHECK (family_size >= 0),
    rejected_null_count INTEGER NOT NULL CHECK (
        rejected_null_count >= 0 AND rejected_null_count <= family_size
    ),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, analysis_config_hash, adapter_config_hash, report_config_hash)
);

CREATE INDEX IF NOT EXISTS idx_range_confirmatory_reports_plan
ON range_confirmatory_reports(plan_id, report_id);
