CREATE TABLE IF NOT EXISTS option_chain_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    underlying TEXT NOT NULL,
    as_of TEXT NOT NULL,
    underlying_price TEXT NOT NULL,
    source TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_series_snapshots (
    snapshot_id TEXT NOT NULL REFERENCES option_chain_snapshots(snapshot_id),
    contract_id TEXT NOT NULL,
    expiration TEXT NOT NULL,
    strike TEXT NOT NULL,
    right_type TEXT NOT NULL,
    quote_observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, contract_id)
);

CREATE TABLE IF NOT EXISTS option_screen_results (
    result_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES option_chain_snapshots(snapshot_id),
    known_at TEXT NOT NULL,
    horizon TEXT NOT NULL,
    selected_contract_id TEXT,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_option_screen_results_order
    ON option_screen_results(known_at, result_id);
