CREATE TABLE IF NOT EXISTS levels (
    level_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    known_at TEXT NOT NULL,
    lower_price TEXT NOT NULL,
    upper_price TEXT NOT NULL,
    kind TEXT NOT NULL,
    confluence_score TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pattern_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    observation_id TEXT NOT NULL REFERENCES feature_snapshots(observation_id),
    instance_id TEXT NOT NULL,
    known_at TEXT NOT NULL,
    pattern_family TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    pattern_version TEXT NOT NULL,
    prior_state TEXT,
    new_state TEXT NOT NULL,
    direction TEXT NOT NULL,
    reference_level TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(run_id, instance_id, known_at)
);

CREATE INDEX IF NOT EXISTS idx_levels_asof
    ON levels(run_id, symbol, timeframe, known_at);
CREATE INDEX IF NOT EXISTS idx_pattern_instance
    ON pattern_events(run_id, instance_id, known_at);
