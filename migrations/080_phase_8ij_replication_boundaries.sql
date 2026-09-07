CREATE TABLE IF NOT EXISTS replication_provider_manifests (
    manifest_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    dataset_revision TEXT NOT NULL,
    known_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(provider_id, dataset_revision)
);

CREATE TABLE IF NOT EXISTS replication_universe_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    provider_manifest_id TEXT NOT NULL REFERENCES replication_provider_manifests(manifest_id),
    universe_name TEXT NOT NULL,
    as_of TEXT NOT NULL,
    known_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replication_universe_memberships (
    snapshot_id TEXT NOT NULL REFERENCES replication_universe_snapshots(snapshot_id),
    instrument_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    status TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS replication_data_bindings (
    binding_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL UNIQUE REFERENCES range_replication_collections(collection_id),
    provider_manifest_id TEXT NOT NULL REFERENCES replication_provider_manifests(manifest_id),
    universe_snapshot_id TEXT NOT NULL REFERENCES replication_universe_snapshots(snapshot_id),
    bound_at TEXT NOT NULL,
    binding_hash TEXT NOT NULL,
    data_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replication_role_credentials (
    credential_id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    role TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    issuer_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(principal_id, role, credential_id)
);

CREATE TABLE IF NOT EXISTS replication_signed_attestations (
    attestation_id TEXT PRIMARY KEY,
    subject_hash TEXT NOT NULL,
    credential_id TEXT NOT NULL REFERENCES replication_role_credentials(credential_id),
    principal_id TEXT NOT NULL,
    role TEXT NOT NULL,
    signed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replication_sealed_outcomes (
    envelope_id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES range_replication_collections(collection_id),
    prediction_id TEXT NOT NULL UNIQUE REFERENCES range_replication_predictions(prediction_id),
    key_id TEXT NOT NULL,
    sealed_at TEXT NOT NULL,
    associated_data_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replication_access_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    principal_id TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    prior_event_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_replication_universe_asof
ON replication_universe_snapshots(universe_name, as_of, known_at);

CREATE INDEX IF NOT EXISTS idx_replication_access_chain
ON replication_access_events(sequence, event_hash);
