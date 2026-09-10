CREATE TABLE IF NOT EXISTS paper_sandbox_stage_leases (
    lease_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    authorization_assessment_id TEXT NOT NULL UNIQUE REFERENCES paper_stage_authorization_assessments(assessment_id),
    plan_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    lease_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY (plan_id, stage_id) REFERENCES paper_rollout_stages(plan_id, stage_id)
);
CREATE TABLE IF NOT EXISTS paper_sandbox_lease_revocations (
    revocation_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL UNIQUE REFERENCES paper_sandbox_stage_leases(lease_id),
    revoked_at TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_sandbox_lease_assessments (
    assessment_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL REFERENCES paper_sandbox_stage_leases(lease_id),
    revocation_id TEXT REFERENCES paper_sandbox_lease_revocations(revocation_id),
    evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (lease_id, evaluated_at)
);
