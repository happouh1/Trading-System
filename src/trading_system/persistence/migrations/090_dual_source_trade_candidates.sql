CREATE TABLE IF NOT EXISTS burn_in_trade_evidence_candidates (
    candidate_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    decision_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('WEBULL_SANDBOX', 'SHADOW_SIMULATED')),
    source_trade_id TEXT NOT NULL,
    entry_known_at TEXT NOT NULL,
    exit_known_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    source_record_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    code_version TEXT NOT NULL,
    simulation_model_hash TEXT,
    schema_version TEXT NOT NULL CHECK (schema_version = 'DUAL_SOURCE_TRADE_CANDIDATE.1.0'),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(plan_id, source, source_trade_id),
    CHECK (entry_known_at < exit_known_at AND exit_known_at <= recorded_at),
    CHECK ((source = 'SHADOW_SIMULATED' AND simulation_model_hash IS NOT NULL)
        OR (source = 'WEBULL_SANDBOX' AND simulation_model_hash IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_burn_in_trade_candidates_plan
    ON burn_in_trade_evidence_candidates(plan_id, source, recorded_at, candidate_id);
