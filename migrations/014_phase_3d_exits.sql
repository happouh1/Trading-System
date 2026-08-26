CREATE TABLE IF NOT EXISTS webull_managed_positions (
    managed_position_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    entry_intent_id TEXT NOT NULL,
    entry_client_order_id TEXT NOT NULL,
    entry_broker_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    filled_quantity INTEGER NOT NULL,
    remaining_quantity INTEGER NOT NULL,
    entry_price TEXT NOT NULL,
    initial_stop_adjusted TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    code_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, entry_intent_id),
    UNIQUE(session_id, entry_client_order_id)
);

CREATE TABLE IF NOT EXISTS webull_position_events (
    position_event_id TEXT PRIMARY KEY,
    managed_position_id TEXT NOT NULL REFERENCES webull_managed_positions(managed_position_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL,
    state TEXT NOT NULL,
    remaining_quantity INTEGER NOT NULL,
    reason TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_position_events_latest
    ON webull_position_events(session_id, managed_position_id, occurred_at);

CREATE TABLE IF NOT EXISTS webull_exit_intents (
    exit_intent_id TEXT PRIMARY KEY,
    managed_position_id TEXT NOT NULL REFERENCES webull_managed_positions(managed_position_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    reason TEXT NOT NULL,
    signal_candle_id TEXT NOT NULL,
    known_at TEXT NOT NULL,
    scheduled_open TEXT NOT NULL,
    requested_quantity INTEGER NOT NULL,
    evidence_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, managed_position_id, reason, known_at)
);

CREATE TABLE IF NOT EXISTS webull_protective_stop_versions (
    stop_version_id TEXT PRIMARY KEY,
    managed_position_id TEXT NOT NULL REFERENCES webull_managed_positions(managed_position_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    client_order_id TEXT NOT NULL,
    known_at TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    adjusted_stop TEXT NOT NULL,
    adjustment_factor TEXT NOT NULL,
    raw_stop TEXT NOT NULL,
    tick_size TEXT NOT NULL,
    source_candle_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, managed_position_id, request_hash)
);
CREATE INDEX IF NOT EXISTS idx_webull_stop_versions_latest
    ON webull_protective_stop_versions(session_id, managed_position_id, known_at);

CREATE TABLE IF NOT EXISTS webull_broker_action_events (
    broker_action_id TEXT PRIMARY KEY,
    managed_position_id TEXT NOT NULL REFERENCES webull_managed_positions(managed_position_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    action_kind TEXT NOT NULL,
    event_type TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_actions_latest
    ON webull_broker_action_events(session_id, managed_position_id, client_order_id, occurred_at);

CREATE TABLE IF NOT EXISTS webull_flatten_authorizations (
    flatten_auth_id TEXT PRIMARY KEY,
    managed_position_id TEXT NOT NULL REFERENCES webull_managed_positions(managed_position_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    reconciliation_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used_at TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, managed_position_id, reconciliation_id)
);

CREATE TABLE IF NOT EXISTS webull_exit_authorizations (
    authorization_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    config_hash TEXT NOT NULL,
    capability_hash TEXT NOT NULL,
    reconciliation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, config_hash, capability_hash, reconciliation_id)
);

CREATE TABLE IF NOT EXISTS webull_position_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    managed_position_id TEXT NOT NULL REFERENCES webull_managed_positions(managed_position_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL,
    expected_quantity INTEGER NOT NULL,
    actual_quantity INTEGER NOT NULL,
    matched INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_position_reconciliation_latest
    ON webull_position_reconciliations(session_id, managed_position_id, occurred_at);
