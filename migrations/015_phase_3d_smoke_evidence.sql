CREATE TABLE IF NOT EXISTS webull_smoke_captures (
    capture_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES paper_sessions(session_id),
    case_id TEXT NOT NULL,
    case_sequence INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    adjustment_factor TEXT NOT NULL,
    capture_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_smoke_capture_session
    ON webull_smoke_captures(session_id, case_sequence, captured_at);

CREATE TABLE IF NOT EXISTS webull_smoke_reviews (
    review_id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES webull_smoke_captures(capture_id),
    reviewed_at TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    notes TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_webull_smoke_review_capture
    ON webull_smoke_reviews(capture_id, reviewed_at);
