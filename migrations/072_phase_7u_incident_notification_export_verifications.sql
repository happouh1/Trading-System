CREATE TABLE IF NOT EXISTS reviewed_range_catalog_incident_notification_export_verifications (
    verification_id TEXT PRIMARY KEY,
    notification_export_id TEXT NOT NULL
        REFERENCES reviewed_range_catalog_incident_notification_exports(notification_export_id),
    incident_id TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED', 'FAILED')),
    expected_hash TEXT NOT NULL,
    actual_hash TEXT,
    reasons_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    export_config_hash TEXT NOT NULL,
    notification_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviewed_catalog_incident_notification_export_verifications
ON reviewed_range_catalog_incident_notification_export_verifications(
    notification_export_id, verified_at, verification_id
);
