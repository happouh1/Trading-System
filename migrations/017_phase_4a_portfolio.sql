CREATE TABLE IF NOT EXISTS portfolio_states (
    portfolio_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, as_of)
);

CREATE TABLE IF NOT EXISTS portfolio_assessments (
    assessment_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    known_at TEXT NOT NULL,
    strategy_class TEXT NOT NULL,
    action TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY (portfolio_id, known_at)
        REFERENCES portfolio_states(portfolio_id, as_of)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_assessments_order
    ON portfolio_assessments(portfolio_id, known_at, assessment_id);
