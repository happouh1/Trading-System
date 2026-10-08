CREATE TABLE IF NOT EXISTS webull_automatic_submission_cycles (
    cycle_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    intent_id TEXT,
    client_order_id TEXT,
    quantity INTEGER NOT NULL,
    config_hash TEXT NOT NULL,
    network_used INTEGER NOT NULL,
    broker_write_performed INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_webull_auto_submit_session_time
ON webull_automatic_submission_cycles(session_id, observed_at);
