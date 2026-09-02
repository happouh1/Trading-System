CREATE TABLE IF NOT EXISTS operations_artifact_trust_proposal_catalogs (
 catalog_id TEXT PRIMARY KEY,
 review_export_id TEXT NOT NULL REFERENCES operations_artifact_trust_review_exports(export_id),
 review_verification_id TEXT NOT NULL REFERENCES operations_artifact_trust_review_export_verifications(verification_id),
 cataloged_at TEXT NOT NULL, status TEXT NOT NULL, source_revision TEXT NOT NULL,
 code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations_artifact_trust_proposal_catalog_entries (
 catalog_id TEXT NOT NULL REFERENCES operations_artifact_trust_proposal_catalogs(catalog_id),
 proposal_id TEXT NOT NULL REFERENCES operations_artifact_trust_policy_proposals(proposal_id),
 sequence INTEGER NOT NULL CHECK(sequence >= 0),
 PRIMARY KEY(catalog_id, proposal_id), UNIQUE(catalog_id, sequence)
);
