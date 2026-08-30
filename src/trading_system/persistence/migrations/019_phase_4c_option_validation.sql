CREATE TABLE IF NOT EXISTS option_validation_cases (
    case_id TEXT PRIMARY KEY,
    screen_result_id TEXT NOT NULL REFERENCES option_screen_results(result_id),
    screen_known_at TEXT NOT NULL,
    selected_contract_id TEXT NOT NULL,
    entry_as_of TEXT NOT NULL,
    exit_as_of TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_validation_results (
    result_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES option_validation_cases(case_id),
    screen_result_id TEXT NOT NULL REFERENCES option_screen_results(result_id),
    known_at TEXT NOT NULL,
    status TEXT NOT NULL,
    net_pnl TEXT,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_backtest_reports (
    report_id TEXT PRIMARY KEY,
    known_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_option_validation_results_order
    ON option_validation_results(known_at, result_id);
