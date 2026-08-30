CREATE TABLE IF NOT EXISTS operations_backup_manifests (
    backup_id TEXT PRIMARY KEY,
    known_at TEXT NOT NULL,
    source_path TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    artifact_hash TEXT NOT NULL,
    artifact_bytes INTEGER NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_restore_verifications (
    verification_id TEXT PRIMARY KEY,
    backup_id TEXT NOT NULL REFERENCES operations_backup_manifests(backup_id),
    known_at TEXT NOT NULL,
    restored_path TEXT NOT NULL,
    status TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_retention_reports (
    report_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    minimum_retention_days INTEGER NOT NULL,
    deletion_performed INTEGER NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operations_backup_known_at
    ON operations_backup_manifests(known_at, backup_id);
CREATE INDEX IF NOT EXISTS idx_operations_restore_backup
    ON operations_restore_verifications(backup_id, known_at, verification_id);
