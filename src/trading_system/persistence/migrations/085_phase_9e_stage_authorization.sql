CREATE TABLE IF NOT EXISTS paper_stage_authorization_requests (
    request_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    rollout_assessment_id TEXT NOT NULL UNIQUE REFERENCES paper_rollout_gate_assessments(assessment_id),
    plan_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY (plan_id, stage_id) REFERENCES paper_rollout_stages(plan_id, stage_id)
);
CREATE TABLE IF NOT EXISTS paper_stage_review_attestations (
    attestation_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES paper_stage_authorization_requests(request_id),
    credential_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    role TEXT NOT NULL,
    signed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (request_id, role)
);
CREATE TABLE IF NOT EXISTS paper_stage_authorization_assessments (
    assessment_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE REFERENCES paper_stage_authorization_requests(request_id),
    plan_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY (plan_id, stage_id) REFERENCES paper_rollout_stages(plan_id, stage_id)
);
