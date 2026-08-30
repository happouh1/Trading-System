CREATE TABLE IF NOT EXISTS option_capital_runs (
    run_id TEXT PRIMARY KEY,
    starting_cash TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    phase4c_config_hash TEXT NOT NULL,
    phase4e_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_capital_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES option_capital_runs(run_id),
    case_id TEXT NOT NULL REFERENCES option_validation_cases(case_id),
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_capital_reports (
    report_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES option_capital_runs(run_id),
    known_at TEXT NOT NULL,
    ending_cash TEXT NOT NULL,
    realized_net_pnl TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_option_capital_events_run_time
    ON option_capital_events(run_id, occurred_at, event_id);
