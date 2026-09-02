CREATE TABLE IF NOT EXISTS operations_artifact_trust_policy_proposals (
 proposal_id TEXT PRIMARY KEY,
 review_export_id TEXT NOT NULL REFERENCES operations_artifact_trust_review_exports(export_id),
 review_verification_id TEXT NOT NULL REFERENCES operations_artifact_trust_review_export_verifications(verification_id),
 proposed_at TEXT NOT NULL, status TEXT NOT NULL, source_revision TEXT NOT NULL,
 code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
