CREATE TABLE IF NOT EXISTS range_replication_collections (
    collection_id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL UNIQUE,
    registered_at TEXT NOT NULL,
    collection_start TEXT NOT NULL,
    collection_end TEXT NOT NULL,
    state TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS range_replication_collection_events (
    event_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES range_replication_collections(collection_id),
    occurred_at TEXT NOT NULL,
    prior_state TEXT,
    new_state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (collection_id, new_state)
);

CREATE TABLE IF NOT EXISTS range_replication_predictions (
    prediction_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES range_replication_collections(collection_id),
    hypothesis_id TEXT NOT NULL,
    box_id TEXT NOT NULL,
    known_at TEXT NOT NULL,
    earliest_outcome_at TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE (collection_id, hypothesis_id, box_id, prediction_id)
);

CREATE TABLE IF NOT EXISTS range_replication_outcomes_blinded_test_only (
    outcome_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES range_replication_collections(collection_id),
    prediction_id TEXT NOT NULL UNIQUE REFERENCES range_replication_predictions(prediction_id),
    known_at TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS range_replication_collection_freezes (
    freeze_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL UNIQUE REFERENCES range_replication_collections(collection_id),
    frozen_at TEXT NOT NULL,
    prediction_root_hash TEXT NOT NULL,
    outcome_root_hash TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_range_replication_predictions_collection
ON range_replication_predictions(collection_id, hypothesis_id, prediction_id);
