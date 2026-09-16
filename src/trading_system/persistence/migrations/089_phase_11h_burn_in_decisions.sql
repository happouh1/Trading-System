CREATE TABLE IF NOT EXISTS burn_in_shadow_decision_cycles (
    cycle_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    observed_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    source_1h_candles INTEGER NOT NULL,
    derived_candles INTEGER NOT NULL,
    processed_candles INTEGER NOT NULL,
    emitted_decisions INTEGER NOT NULL,
    directional_decisions INTEGER NOT NULL,
    staged_shadow_intents INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, observed_at, config_hash)
);
CREATE INDEX IF NOT EXISTS idx_burn_in_shadow_decision_cycles_session
    ON burn_in_shadow_decision_cycles(session_id, observed_at, cycle_id);
