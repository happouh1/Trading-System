CREATE TABLE IF NOT EXISTS operations_schedules (
    job_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    component TEXT NOT NULL,
    mode TEXT NOT NULL,
    first_due_at TEXT NOT NULL,
    cadence_seconds INTEGER NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_schedule_plans (
    plan_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_health_observations (
    observation_id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_fingerprint TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_internal_alerts (
    alert_id TEXT PRIMARY KEY,
    known_at TEXT NOT NULL,
    component TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_monitor_reports (
    report_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    status TEXT NOT NULL,
    schedule_plan_id TEXT NOT NULL REFERENCES operations_schedule_plans(plan_id),
    source_revision TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_monitor_reports_time
    ON operations_monitor_reports(as_of, report_id);
