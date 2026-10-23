CREATE TABLE IF NOT EXISTS paper_shadow_operation_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('POST_CLOSE', 'AUDIT')),
    state TEXT NOT NULL CHECK (state IN ('STARTED', 'PROGRESS', 'COMPLETED', 'FAILED')),
    stage TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    details_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_shadow_operation_events_session
    ON paper_shadow_operation_events(session_id, operation, observed_at, event_id);
