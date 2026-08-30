CREATE TABLE IF NOT EXISTS option_experiments (
    experiment_id TEXT PRIMARY KEY,
    source_revision TEXT NOT NULL,
    phase4c_config_hash TEXT NOT NULL,
    phase4d_config_hash TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_experiment_folds (
    fold_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES option_experiments(experiment_id),
    ordinal INTEGER NOT NULL,
    test_end TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, ordinal)
);

CREATE TABLE IF NOT EXISTS option_experiment_assignments (
    assignment_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES option_experiments(experiment_id),
    fold_id TEXT NOT NULL REFERENCES option_experiment_folds(fold_id),
    case_id TEXT NOT NULL REFERENCES option_validation_cases(case_id),
    partition TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(fold_id, case_id)
);

CREATE TABLE IF NOT EXISTS option_fold_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES option_experiments(experiment_id),
    fold_id TEXT NOT NULL REFERENCES option_experiment_folds(fold_id),
    partition TEXT NOT NULL,
    cutoff TEXT NOT NULL,
    phase4c_config_hash TEXT NOT NULL,
    phase4d_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(fold_id, partition)
);

CREATE TABLE IF NOT EXISTS option_experiment_transitions (
    transition_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES option_experiments(experiment_id),
    sequence INTEGER NOT NULL,
    prior_stage TEXT NOT NULL,
    new_stage TEXT NOT NULL,
    frozen_definition_hash TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(experiment_id, sequence),
    UNIQUE(experiment_id, new_stage)
);

CREATE INDEX IF NOT EXISTS idx_option_experiment_evaluations
    ON option_fold_evaluations(experiment_id, partition, cutoff);
