CREATE TABLE IF NOT EXISTS range_entry_outcomes (
    outcome_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    entry_id TEXT NOT NULL REFERENCES range_research_entries(entry_id),
    horizon_bars INTEGER NOT NULL CHECK (horizon_bars > 0),
    label_available_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (entry_id, horizon_bars)
);

CREATE INDEX IF NOT EXISTS idx_range_entry_outcomes_available
ON range_entry_outcomes(run_id, label_available_at, outcome_id);
