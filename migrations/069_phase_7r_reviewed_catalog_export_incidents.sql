CREATE TABLE IF NOT EXISTS reviewed_range_catalog_export_incident_events (
    incident_event_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    catalog_export_id TEXT NOT NULL REFERENCES reviewed_range_catalog_exports(catalog_export_id),
    source_verification_id TEXT NOT NULL
        REFERENCES reviewed_range_catalog_export_verifications(verification_id),
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('OPENED', 'ACKNOWLEDGED', 'RESOLVED')),
    prior_state TEXT CHECK (prior_state IS NULL OR prior_state IN ('OPEN', 'ACKNOWLEDGED')),
    new_state TEXT NOT NULL CHECK (new_state IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
    actor_id TEXT NOT NULL,
    note TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reviewed_catalog_export_incident_open
ON reviewed_range_catalog_export_incident_events(incident_id)
WHERE event_type = 'OPENED';

CREATE INDEX IF NOT EXISTS idx_reviewed_catalog_export_incident_history
ON reviewed_range_catalog_export_incident_events(incident_id, occurred_at, incident_event_id);

CREATE INDEX IF NOT EXISTS idx_reviewed_catalog_export_incident_export
ON reviewed_range_catalog_export_incident_events(catalog_export_id, occurred_at, incident_event_id);
