CREATE TABLE IF NOT EXISTS range_research_entries (
    entry_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    evidence_id TEXT NOT NULL REFERENCES range_reclaim_evidence(evidence_id),
    source_candle_id TEXT NOT NULL REFERENCES candles(candle_id),
    entry_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('FILLED', 'CANCELLED_ADVERSE_GAP')),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (evidence_id)
);

CREATE INDEX IF NOT EXISTS idx_range_research_entries_asof
ON range_research_entries(run_id, entry_time, entry_id);
