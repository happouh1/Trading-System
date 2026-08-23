CREATE TABLE IF NOT EXISTS paper_sessions (
    session_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, mode TEXT NOT NULL,
    code_version TEXT NOT NULL, config_hash TEXT NOT NULL, data_revision TEXT NOT NULL,
    calendar_version TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_transitions (
    transition_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    prior_state TEXT NOT NULL, new_state TEXT NOT NULL, occurred_at TEXT NOT NULL,
    reason TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_intents (
    intent_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    trade_plan_id TEXT NOT NULL, scheduled_open TEXT NOT NULL, status TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(session_id, trade_plan_id, scheduled_open)
);
CREATE TABLE IF NOT EXISTS paper_adapter_events (
    adapter_event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    intent_id TEXT, event_type TEXT NOT NULL, occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, matched INTEGER NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_checkpoints (
    checkpoint_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    candle_id TEXT NOT NULL, timeframe TEXT NOT NULL, known_at TEXT NOT NULL,
    state_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(session_id, candle_id)
);
CREATE TABLE IF NOT EXISTS paper_incidents (
    incident_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_heartbeats (
    heartbeat_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    occurred_at TEXT NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_orders (
    paper_order_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    intent_id TEXT NOT NULL REFERENCES paper_intents(intent_id), status TEXT NOT NULL,
    occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_fills (
    paper_fill_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    paper_order_id TEXT NOT NULL REFERENCES paper_orders(paper_order_id), occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_reports (
    report_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    created_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
