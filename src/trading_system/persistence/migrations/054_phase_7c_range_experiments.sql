CREATE TABLE IF NOT EXISTS range_experiment_plans (
    plan_id TEXT PRIMARY KEY,
    registration_run_id TEXT NOT NULL REFERENCES runs(run_id),
    registered_at TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS range_experiment_assignments (
    assignment_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    fold_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL REFERENCES range_box_outcomes(outcome_id),
    box_id TEXT NOT NULL REFERENCES range_boxes(box_id),
    partition TEXT NOT NULL CHECK (partition IN ('TRAIN', 'VALIDATION', 'TEST', 'EXCLUDED')),
    cluster_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, fold_id, outcome_id)
);

CREATE TABLE IF NOT EXISTS range_experiment_gates (
    gate_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    fold_id TEXT NOT NULL,
    partition TEXT NOT NULL CHECK (partition IN ('TRAIN', 'VALIDATION', 'TEST')),
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_range_experiment_assignments_partition
ON range_experiment_assignments(plan_id, fold_id, partition);
