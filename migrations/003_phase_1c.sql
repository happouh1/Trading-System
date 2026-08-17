CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    observation_id TEXT NOT NULL REFERENCES feature_snapshots(observation_id),
    known_at TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence TEXT NOT NULL,
    setup_quality TEXT NOT NULL,
    entry_quality TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(run_id, observation_id)
);

CREATE TABLE IF NOT EXISTS trade_events (
    trade_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    trade_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    event_type TEXT NOT NULL,
    price TEXT,
    quantity TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(run_id, trade_id, event_time, event_type)
);

CREATE INDEX IF NOT EXISTS idx_decisions_asof ON decisions(run_id, known_at);
CREATE INDEX IF NOT EXISTS idx_trade_lifecycle ON trade_events(run_id, trade_id, event_time);
