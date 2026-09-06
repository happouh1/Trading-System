CREATE TABLE IF NOT EXISTS range_confirmatory_tests (
    test_id TEXT PRIMARY KEY,
    summary_id TEXT NOT NULL REFERENCES range_cohort_summaries(summary_id),
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    fold_id TEXT NOT NULL,
    null_rejected INTEGER NOT NULL CHECK (null_rejected IN (0, 1)),
    analysis_config_hash TEXT NOT NULL,
    adapter_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (summary_id, analysis_config_hash, adapter_config_hash)
);

CREATE INDEX IF NOT EXISTS idx_range_confirmatory_tests_plan
ON range_confirmatory_tests(plan_id, fold_id, summary_id);
