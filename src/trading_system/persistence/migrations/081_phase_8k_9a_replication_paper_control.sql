CREATE TABLE IF NOT EXISTS range_replication_runs (
    run_id TEXT PRIMARY KEY,
    freeze_id TEXT NOT NULL UNIQUE REFERENCES range_replication_collection_freezes(freeze_id),
    collection_id TEXT NOT NULL REFERENCES range_replication_collections(collection_id),
    executed_at TEXT NOT NULL,
    family_input_hash TEXT NOT NULL,
    result_root_hash TEXT NOT NULL,
    result_count INTEGER NOT NULL CHECK (result_count > 0),
    state TEXT NOT NULL CHECK (state = 'SEALED'),
    runner_config_hash TEXT NOT NULL,
    statistics_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS range_replication_run_results (
    run_id TEXT NOT NULL REFERENCES range_replication_runs(run_id),
    result_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    state TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    PRIMARY KEY (run_id, result_id),
    UNIQUE (run_id, hypothesis_id)
);

CREATE TABLE IF NOT EXISTS paper_operator_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    observed_at TEXT NOT NULL,
    runtime_state TEXT NOT NULL,
    health TEXT NOT NULL,
    replication_status_hash TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_operator_jobs (
    job_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    component TEXT NOT NULL,
    due_at TEXT NOT NULL,
    cadence_seconds INTEGER NOT NULL CHECK (cadence_seconds > 0),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (session_id, component, due_at)
);
