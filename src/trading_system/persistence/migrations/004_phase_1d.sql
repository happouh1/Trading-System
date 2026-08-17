CREATE TABLE IF NOT EXISTS replay_checkpoints (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    last_close_time TEXT NOT NULL,
    processed_candles INTEGER NOT NULL,
    state_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    observation_id TEXT NOT NULL REFERENCES feature_snapshots(observation_id),
    label_version TEXT NOT NULL,
    horizon_bars INTEGER NOT NULL,
    forward_return TEXT,
    mfe_r TEXT,
    mae_r TEXT,
    time_to_1r INTEGER,
    time_to_2r INTEGER,
    outcome_label TEXT,
    label_available_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(run_id, observation_id, label_version, horizon_bars)
);

CREATE INDEX IF NOT EXISTS idx_outcomes_observation
ON outcomes(observation_id, horizon_bars);
