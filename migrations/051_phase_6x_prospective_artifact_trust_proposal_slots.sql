CREATE TABLE IF NOT EXISTS operations_artifact_trust_proposal_plans (
 plan_id TEXT PRIMARY KEY, plan_name TEXT NOT NULL, review_export_id TEXT NOT NULL,
 review_verification_id TEXT NOT NULL, registered_at TEXT NOT NULL, slot_root_hash TEXT NOT NULL,
 source_revision TEXT NOT NULL, code_version TEXT NOT NULL, config_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations_artifact_trust_proposal_slots (
 plan_id TEXT NOT NULL REFERENCES operations_artifact_trust_proposal_plans(plan_id),
 slot_id TEXT NOT NULL, opens_at TEXT NOT NULL, closes_at TEXT NOT NULL,
 payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL, PRIMARY KEY(plan_id, slot_id),
 UNIQUE(plan_id, opens_at, closes_at)
);
CREATE TABLE IF NOT EXISTS operations_artifact_trust_proposal_bindings (
 binding_id TEXT PRIMARY KEY,
 plan_id TEXT NOT NULL REFERENCES operations_artifact_trust_proposal_plans(plan_id),
 slot_id TEXT NOT NULL, proposal_id TEXT NOT NULL REFERENCES operations_artifact_trust_policy_proposals(proposal_id),
 bound_at TEXT NOT NULL, source_revision TEXT NOT NULL, code_version TEXT NOT NULL,
 config_hash TEXT NOT NULL, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
 UNIQUE(plan_id, slot_id), UNIQUE(plan_id, proposal_id)
);
