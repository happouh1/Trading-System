CREATE TABLE IF NOT EXISTS operations_prospective_review_plans (
    plan_id TEXT PRIMARY KEY, catalog_name TEXT NOT NULL, registered_at TEXT NOT NULL,
    slot_root_hash TEXT NOT NULL, source_revision TEXT NOT NULL, code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations_prospective_review_slots (
    plan_id TEXT NOT NULL REFERENCES operations_prospective_review_plans(plan_id),
    slot_id TEXT NOT NULL, expected_as_of TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL, PRIMARY KEY (plan_id, slot_id), UNIQUE (plan_id, expected_as_of)
);
CREATE TABLE IF NOT EXISTS operations_prospective_review_bindings (
    binding_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES operations_prospective_review_plans(plan_id),
    slot_id TEXT NOT NULL, bundle_id TEXT NOT NULL, verification_id TEXT NOT NULL,
    bound_at TEXT NOT NULL, source_revision TEXT NOT NULL, code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
    UNIQUE (plan_id, slot_id), UNIQUE (plan_id, bundle_id)
);
