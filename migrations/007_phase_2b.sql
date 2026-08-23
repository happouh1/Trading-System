CREATE TABLE IF NOT EXISTS experiment_transitions (
    transition_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    prior_stage TEXT NOT NULL, new_stage TEXT NOT NULL, occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, new_stage)
);
CREATE TABLE IF NOT EXISTS experiment_lineage (
    experiment_id TEXT PRIMARY KEY REFERENCES experiments(experiment_id),
    parent_experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    reason TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiment_cohorts (
    cohort_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    specification_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, specification_hash)
);
CREATE TABLE IF NOT EXISTS fold_assignments (
    assignment_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    fold_id TEXT NOT NULL REFERENCES experiment_folds(fold_id), row_id TEXT NOT NULL,
    partition TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, fold_id, row_id)
);
CREATE TABLE IF NOT EXISTS experiment_checkpoints (
    checkpoint_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    stage TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, stage)
);
CREATE TABLE IF NOT EXISTS experiment_exclusions (
    exclusion_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    fold_id TEXT REFERENCES experiment_folds(fold_id), row_id TEXT NOT NULL, reason TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, fold_id, row_id, reason)
);
CREATE TABLE IF NOT EXISTS experiment_reports (
    report_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    stage TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS symbol_holdout_assignments (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id), symbol TEXT NOT NULL,
    bucket INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    PRIMARY KEY(experiment_id, symbol)
);
