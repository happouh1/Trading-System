CREATE TABLE IF NOT EXISTS operations_artifact_trust_review_exports (
 export_id TEXT PRIMARY KEY,
 signing_request_id TEXT NOT NULL REFERENCES operations_artifact_signing_requests(request_id),
 exported_at TEXT NOT NULL, artifact_path TEXT NOT NULL, artifact_hash TEXT NOT NULL,
 source_revision TEXT NOT NULL, code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 UNIQUE(signing_request_id)
);
CREATE TABLE IF NOT EXISTS operations_artifact_trust_review_export_verifications (
 verification_id TEXT PRIMARY KEY,
 export_id TEXT NOT NULL REFERENCES operations_artifact_trust_review_exports(export_id),
 verified_at TEXT NOT NULL, status TEXT NOT NULL, source_revision TEXT NOT NULL,
 code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
