CREATE TABLE IF NOT EXISTS webull_smoke_operation_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    case_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    event_type TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_smoke_operation_session
    ON webull_smoke_operation_events(session_id, case_id, occurred_at);
