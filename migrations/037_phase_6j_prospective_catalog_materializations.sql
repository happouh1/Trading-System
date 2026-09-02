CREATE TABLE IF NOT EXISTS operations_prospective_catalog_materializations (
    materialization_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE REFERENCES operations_prospective_review_plans(plan_id),
    catalog_id TEXT NOT NULL UNIQUE REFERENCES operations_observation_audit_review_catalogs(catalog_id),
    materialized_at TEXT NOT NULL, source_revision TEXT NOT NULL, code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
