CREATE TABLE IF NOT EXISTS operations_artifact_trust_policies (
 policy_id TEXT PRIMARY KEY, registered_at TEXT NOT NULL, status TEXT NOT NULL,
 source_revision TEXT NOT NULL, code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations_artifact_signing_requests (
 request_id TEXT PRIMARY KEY,
 policy_id TEXT NOT NULL REFERENCES operations_artifact_trust_policies(policy_id),
 export_id TEXT NOT NULL REFERENCES operations_prospective_review_bundle_chain_exports(export_id),
 export_verification_id TEXT NOT NULL REFERENCES operations_prospective_review_bundle_chain_export_verifications(verification_id),
 requested_at TEXT NOT NULL, status TEXT NOT NULL, source_revision TEXT NOT NULL,
 code_version TEXT NOT NULL, config_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 UNIQUE(policy_id,export_id,export_verification_id)
);
