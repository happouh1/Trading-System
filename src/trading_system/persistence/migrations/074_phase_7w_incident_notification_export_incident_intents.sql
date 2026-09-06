CREATE TABLE IF NOT EXISTS reviewed_range_catalog_incident_notification_export_incident_intents (
    notification_intent_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    incident_event_id TEXT NOT NULL REFERENCES
        reviewed_range_catalog_incident_notification_export_incident_events(incident_event_id),
    notification_export_id TEXT NOT NULL REFERENCES
        reviewed_range_catalog_incident_notification_exports(notification_export_id),
    source_verification_id TEXT NOT NULL REFERENCES
        reviewed_range_catalog_incident_notification_export_verifications(verification_id),
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

CREATE INDEX IF NOT EXISTS idx_notification_export_incident_intent_history
ON reviewed_range_catalog_incident_notification_export_incident_intents(
    incident_id, occurred_at, notification_intent_id
);
