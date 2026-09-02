CREATE TABLE IF NOT EXISTS operations_prospective_chain_exports (
 export_id TEXT PRIMARY KEY, materialization_id TEXT NOT NULL REFERENCES operations_prospective_catalog_materializations(materialization_id),
 exported_at TEXT NOT NULL, artifact_path TEXT NOT NULL, artifact_hash TEXT NOT NULL,
 source_revision TEXT NOT NULL, code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operations_prospective_chain_export_verifications (
 verification_id TEXT PRIMARY KEY, export_id TEXT NOT NULL REFERENCES operations_prospective_chain_exports(export_id),
 verified_at TEXT NOT NULL, status TEXT NOT NULL, source_revision TEXT NOT NULL,
 code_version TEXT NOT NULL, config_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL);
