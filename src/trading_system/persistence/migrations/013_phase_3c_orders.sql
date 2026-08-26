CREATE TABLE IF NOT EXISTS webull_submission_events (
    submission_event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    intent_id TEXT NOT NULL REFERENCES paper_intents(intent_id),
    client_order_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_submission_intent
    ON webull_submission_events(session_id, intent_id, occurred_at);

CREATE TABLE IF NOT EXISTS webull_entry_releases (
    release_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    intent_id TEXT NOT NULL REFERENCES paper_intents(intent_id),
    request_hash TEXT NOT NULL,
    provider_timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    approved INTEGER NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, intent_id, request_hash)
);

CREATE TABLE IF NOT EXISTS webull_executions (
    execution_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    client_order_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    cumulative_quantity INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, client_order_id, cumulative_quantity)
);
