CREATE TABLE IF NOT EXISTS paper_shadow_daily_audits (
    audit_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    plan_id TEXT NOT NULL,
    market_day TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    missing_components_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    broker_write_detected INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_paper_shadow_daily_audits_plan
    ON paper_shadow_daily_audits(plan_id, market_day, audit_id);
