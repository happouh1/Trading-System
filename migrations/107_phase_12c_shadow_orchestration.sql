CREATE TABLE IF NOT EXISTS paper_shadow_orchestration_receipts (
    receipt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    plan_id TEXT NOT NULL,
    market_day TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('START', 'POST_CLOSE')),
    scheduled_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    worker_cycle_id TEXT,
    decision_cycle_id TEXT,
    status TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    network_read_used INTEGER NOT NULL,
    broker_write_performed INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(session_id, action)
);

CREATE INDEX IF NOT EXISTS idx_shadow_orchestration_plan_day
ON paper_shadow_orchestration_receipts(plan_id, market_day, action);
