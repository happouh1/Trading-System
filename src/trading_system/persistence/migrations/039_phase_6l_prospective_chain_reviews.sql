CREATE TABLE IF NOT EXISTS operations_prospective_chain_reviews (
    review_id TEXT PRIMARY KEY,
    export_id TEXT NOT NULL REFERENCES operations_prospective_chain_exports(export_id),
    verification_id TEXT NOT NULL REFERENCES operations_prospective_chain_export_verifications(verification_id),
    reviewer_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    verdict TEXT NOT NULL,
    eligible_for_summary INTEGER NOT NULL,
    supersedes_review_id TEXT REFERENCES operations_prospective_chain_reviews(review_id),
    source_revision TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prospective_chain_reviews_export
    ON operations_prospective_chain_reviews(export_id, reviewed_at, review_id);

CREATE INDEX IF NOT EXISTS idx_prospective_chain_reviews_reviewer
    ON operations_prospective_chain_reviews(reviewer_id, reviewed_at, review_id);
