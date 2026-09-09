CREATE TABLE IF NOT EXISTS paper_certification_dossiers (
    dossier_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    burn_in_assessment_id TEXT NOT NULL UNIQUE REFERENCES paper_burn_in_assessments(assessment_id),
    declared_at TEXT NOT NULL, dossier_hash TEXT NOT NULL, config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_certification_attestations (
    attestation_id TEXT PRIMARY KEY, dossier_id TEXT NOT NULL REFERENCES paper_certification_dossiers(dossier_id),
    credential_id TEXT NOT NULL, principal_id TEXT NOT NULL, role TEXT NOT NULL, signed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, UNIQUE(dossier_id, role)
);
CREATE TABLE IF NOT EXISTS paper_certification_assessments (
    assessment_id TEXT PRIMARY KEY, dossier_id TEXT NOT NULL UNIQUE REFERENCES paper_certification_dossiers(dossier_id),
    evaluated_at TEXT NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
