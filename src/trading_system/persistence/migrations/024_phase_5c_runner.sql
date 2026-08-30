CREATE TABLE IF NOT EXISTS operations_run_requests (
    request_id TEXT PRIMARY KEY,
    schedule_plan_id TEXT NOT NULL REFERENCES operations_schedule_plans(plan_id),
    schedule_job_id TEXT NOT NULL REFERENCES operations_schedules(job_id),
    due_at TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    source_revision TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_run_attempts (
    attempt_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES operations_run_requests(request_id),
    attempt_number INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    exit_code INTEGER,
    result_json TEXT NOT NULL,
    stdout_hash TEXT NOT NULL,
    stderr_hash TEXT NOT NULL,
    next_retry_at TEXT,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (request_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS operations_run_leases (
    schedule_job_id TEXT PRIMARY KEY REFERENCES operations_schedules(job_id),
    request_id TEXT NOT NULL REFERENCES operations_run_requests(request_id),
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_run_attempts_request
    ON operations_run_attempts(request_id, attempt_number);
