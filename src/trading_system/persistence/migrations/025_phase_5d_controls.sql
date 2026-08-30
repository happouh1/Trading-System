CREATE TABLE IF NOT EXISTS operations_approval_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES operations_run_requests(request_id),
    operator_id TEXT NOT NULL,
    action TEXT NOT NULL,
    known_at TEXT NOT NULL,
    expires_at TEXT,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_kill_switch_events (
    event_id TEXT PRIMARY KEY,
    component TEXT,
    action TEXT NOT NULL,
    known_at TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_cancellation_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES operations_run_requests(request_id),
    action TEXT NOT NULL,
    known_at TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_incident_events (
    event_id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL REFERENCES operations_internal_alerts(alert_id),
    action TEXT NOT NULL,
    known_at TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_control_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    request_id TEXT REFERENCES operations_run_requests(request_id),
    status TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_approval_request
    ON operations_approval_events(request_id, known_at, event_id);
CREATE INDEX IF NOT EXISTS idx_operations_incident_alert
    ON operations_incident_events(alert_id, known_at, event_id);
