CREATE TABLE IF NOT EXISTS webull_connection_verifications (
    verification_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, account_id_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webull_envelopes (
    envelope_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    operation TEXT NOT NULL, occurred_at TEXT NOT NULL, request_hash TEXT,
    response_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webull_account_snapshots (
    snapshot_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webull_order_previews (
    preview_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    intent_id TEXT NOT NULL REFERENCES paper_intents(intent_id), request_hash TEXT NOT NULL,
    occurred_at TEXT NOT NULL, accepted INTEGER NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL, UNIQUE(session_id, intent_id, request_hash)
);
CREATE TABLE IF NOT EXISTS webull_client_orders (
    mapping_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    intent_id TEXT NOT NULL REFERENCES paper_intents(intent_id), client_order_id TEXT NOT NULL,
    request_hash TEXT NOT NULL, broker_order_id TEXT, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL, UNIQUE(session_id, client_order_id), UNIQUE(session_id, intent_id)
);
CREATE TABLE IF NOT EXISTS webull_broker_events (
    event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    client_order_id TEXT NOT NULL, occurred_at TEXT NOT NULL, status TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webull_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, matched INTEGER NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webull_transport_incidents (
    incident_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
