CREATE TABLE IF NOT EXISTS paper_burn_in_session_bindings (
    binding_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE REFERENCES paper_sessions(session_id),
    plan_id TEXT NOT NULL,
    baseline_session_id TEXT NOT NULL,
    runtime_lock_hash TEXT NOT NULL,
    started_at TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    data_revision TEXT NOT NULL,
    calendar_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_burn_in_bindings_plan
    ON paper_burn_in_session_bindings(plan_id, started_at, session_id);
