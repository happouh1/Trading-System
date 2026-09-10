CREATE TABLE IF NOT EXISTS paper_staged_rollout_plans (
    plan_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    certification_assessment_id TEXT NOT NULL UNIQUE REFERENCES paper_certification_assessments(assessment_id),
    declared_at TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_rollout_stages (
    plan_id TEXT NOT NULL REFERENCES paper_staged_rollout_plans(plan_id),
    stage_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (plan_id, stage_id),
    UNIQUE (plan_id, sequence)
);
CREATE TABLE IF NOT EXISTS paper_rollout_stage_evidence (
    evidence_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES paper_staged_rollout_plans(plan_id),
    stage_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, stage_id),
    FOREIGN KEY (plan_id, stage_id) REFERENCES paper_rollout_stages(plan_id, stage_id)
);
CREATE TABLE IF NOT EXISTS paper_rollout_gate_assessments (
    assessment_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES paper_staged_rollout_plans(plan_id),
    stage_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL UNIQUE REFERENCES paper_rollout_stage_evidence(evidence_id),
    evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, stage_id),
    FOREIGN KEY (plan_id, stage_id) REFERENCES paper_rollout_stages(plan_id, stage_id)
);
