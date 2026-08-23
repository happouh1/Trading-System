CREATE TABLE IF NOT EXISTS model_experiments (
    model_experiment_id TEXT PRIMARY KEY,
    research_experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    created_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_experiment_lineage (
    model_experiment_id TEXT PRIMARY KEY REFERENCES model_experiments(model_experiment_id),
    parent_model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    reason TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_transitions (
    transition_id TEXT PRIMARY KEY,
    model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    prior_stage TEXT NOT NULL, new_stage TEXT NOT NULL, occurred_at TEXT NOT NULL,
    frozen_manifest_hash TEXT, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(model_experiment_id, new_stage)
);
CREATE TABLE IF NOT EXISTS model_fold_artifacts (
    artifact_id TEXT PRIMARY KEY,
    model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    fold_id TEXT NOT NULL REFERENCES experiment_folds(fold_id), estimator_kind TEXT NOT NULL,
    artifact_path TEXT NOT NULL, artifact_hash TEXT NOT NULL, manifest_json TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(model_experiment_id, fold_id, estimator_kind)
);
CREATE TABLE IF NOT EXISTS model_predictions (
    prediction_id TEXT PRIMARY KEY,
    model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    artifact_id TEXT NOT NULL REFERENCES model_fold_artifacts(artifact_id),
    observation_id TEXT NOT NULL, fold_id TEXT NOT NULL, partition TEXT NOT NULL,
    known_at TEXT NOT NULL, probability REAL NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(model_experiment_id, artifact_id, observation_id, partition)
);
CREATE TABLE IF NOT EXISTS model_metrics (
    metric_id TEXT PRIMARY KEY,
    model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    fold_id TEXT NOT NULL, partition TEXT NOT NULL, estimator_kind TEXT NOT NULL,
    known_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_exclusions (
    exclusion_id TEXT PRIMARY KEY,
    model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    row_id TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE(model_experiment_id, row_id, reason)
);
CREATE TABLE IF NOT EXISTS model_reports (
    report_id TEXT PRIMARY KEY,
    model_experiment_id TEXT NOT NULL REFERENCES model_experiments(model_experiment_id),
    stage TEXT NOT NULL, created_at TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
