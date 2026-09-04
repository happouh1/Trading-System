CREATE TABLE IF NOT EXISTS range_evaluation_assignments (
    assignment_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    outcome_id TEXT NOT NULL REFERENCES range_entry_outcomes(outcome_id),
    fold_id TEXT NOT NULL,
    partition TEXT NOT NULL CHECK (partition IN ('TRAIN', 'VALIDATION', 'TEST', 'EXCLUDED')),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, fold_id, outcome_id)
);

CREATE TABLE IF NOT EXISTS range_cohort_summaries (
    summary_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES range_experiment_plans(plan_id),
    fold_id TEXT NOT NULL,
    partition TEXT NOT NULL CHECK (partition IN ('TRAIN', 'VALIDATION', 'TEST')),
    gate_passed INTEGER NOT NULL CHECK (gate_passed IN (0, 1)),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_range_evaluation_assignments_plan
ON range_evaluation_assignments(plan_id, fold_id, partition, outcome_id);

CREATE INDEX IF NOT EXISTS idx_range_cohort_summaries_plan
ON range_cohort_summaries(plan_id, fold_id, partition, summary_id);
