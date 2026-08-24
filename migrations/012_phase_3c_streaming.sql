CREATE TABLE IF NOT EXISTS webull_stream_notifications (
    notification_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    topic TEXT NOT NULL, symbol TEXT, provider_timestamp TEXT, received_at TEXT NOT NULL,
    raw_payload_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_stream_order
    ON webull_stream_notifications(session_id, symbol, provider_timestamp);
CREATE TABLE IF NOT EXISTS webull_stream_events (
    stream_event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, event_type TEXT NOT NULL, attempt INTEGER NOT NULL,
    delay_seconds INTEGER, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
