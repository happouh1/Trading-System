CREATE TABLE IF NOT EXISTS webull_burn_in_worker_cycles (
    cycle_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    observed_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    history_responses INTEGER NOT NULL,
    completed_bars_seen INTEGER NOT NULL,
    new_bars_persisted INTEGER NOT NULL,
    heartbeat_inserted INTEGER NOT NULL,
    network_used INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, observed_at, config_hash)
);
CREATE INDEX IF NOT EXISTS idx_webull_burn_in_worker_cycles_session
    ON webull_burn_in_worker_cycles(session_id, observed_at, cycle_id);
