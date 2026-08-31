CREATE TABLE IF NOT EXISTS operations_observation_plans (
    plan_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_observation_plan_windows (
    plan_id TEXT NOT NULL REFERENCES operations_observation_plans(plan_id),
    window_id TEXT NOT NULL,
    expected_as_of TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (plan_id, window_id),
    UNIQUE (plan_id, expected_as_of)
);

CREATE TABLE IF NOT EXISTS operations_observation_plan_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES operations_observation_plans(plan_id),
    campaign_report_id TEXT NOT NULL,
    reconciled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    campaign_status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observation_plans_registered
    ON operations_observation_plans(registered_at, plan_id);

CREATE INDEX IF NOT EXISTS idx_observation_plan_windows_time
    ON operations_observation_plan_windows(expected_as_of, plan_id);

CREATE INDEX IF NOT EXISTS idx_observation_reconciliations_report
    ON operations_observation_plan_reconciliations(campaign_report_id, reconciled_at);
