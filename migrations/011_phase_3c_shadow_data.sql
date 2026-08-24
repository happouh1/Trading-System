CREATE TABLE IF NOT EXISTS webull_shadow_bars (
    shadow_bar_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    candle_id TEXT NOT NULL REFERENCES candles(candle_id),
    kind TEXT NOT NULL,
    provider_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    raw_payload_hash TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, candle_id)
);
CREATE INDEX IF NOT EXISTS idx_webull_shadow_asof
    ON webull_shadow_bars(session_id, known_at, candle_id);
