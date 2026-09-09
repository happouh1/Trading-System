CREATE TABLE IF NOT EXISTS paper_burn_in_protocols (
    protocol_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    declared_at TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    definition_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_burn_in_assessments (
    assessment_id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL UNIQUE REFERENCES paper_burn_in_protocols(protocol_id),
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    evaluated_at TEXT NOT NULL,
    state TEXT NOT NULL,
    snapshot_root_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
