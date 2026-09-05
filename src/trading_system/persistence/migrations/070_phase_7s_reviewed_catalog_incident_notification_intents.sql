CREATE TABLE IF NOT EXISTS reviewed_range_catalog_incident_notification_intents (
    notification_intent_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    incident_event_id TEXT NOT NULL
        REFERENCES reviewed_range_catalog_export_incident_events(incident_event_id),
    catalog_export_id TEXT NOT NULL REFERENCES reviewed_range_catalog_exports(catalog_export_id),
    source_verification_id TEXT NOT NULL
        REFERENCES reviewed_range_catalog_export_verifications(verification_id),
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('OPENED', 'ACKNOWLEDGED', 'RESOLVED')),
    incident_state TEXT NOT NULL CHECK (incident_state IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')),
    route TEXT NOT NULL CHECK (route = 'LOCAL_OPERATOR_OUTBOX'),
    delivery_attempt_count INTEGER NOT NULL CHECK (delivery_attempt_count = 0),
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(incident_event_id, config_hash)
);

CREATE INDEX IF NOT EXISTS idx_reviewed_catalog_incident_notification_history
ON reviewed_range_catalog_incident_notification_intents(
    incident_id, occurred_at, notification_intent_id
);
