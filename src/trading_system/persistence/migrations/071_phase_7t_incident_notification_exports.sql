CREATE TABLE IF NOT EXISTS reviewed_range_catalog_incident_notification_exports (
    notification_export_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    opening_incident_event_id TEXT NOT NULL
        REFERENCES reviewed_range_catalog_export_incident_events(incident_event_id),
    catalog_export_id TEXT NOT NULL REFERENCES reviewed_range_catalog_exports(catalog_export_id),
    output_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count > 0),
    intent_count INTEGER NOT NULL CHECK (intent_count > 0),
    notification_config_hash TEXT NOT NULL,
    export_config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(incident_id, output_path, content_hash, export_config_hash)
);

CREATE INDEX IF NOT EXISTS idx_reviewed_catalog_incident_notification_exports_source
ON reviewed_range_catalog_incident_notification_exports(incident_id, notification_export_id);
