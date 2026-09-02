CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_catalog_plans (
    plan_id TEXT PRIMARY KEY,
    catalog_name TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    source_root_hash TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_catalog_plan_sources (
    plan_id TEXT NOT NULL REFERENCES operations_prospective_chain_review_catalog_plans(plan_id),
    bundle_id TEXT NOT NULL,
    verification_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (plan_id, bundle_id)
);

CREATE TABLE IF NOT EXISTS operations_prospective_chain_review_catalog_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES operations_prospective_chain_review_catalog_plans(plan_id),
    catalog_id TEXT NOT NULL,
    reconciled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
