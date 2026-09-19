CREATE TABLE IF NOT EXISTS prospective_entry_requests (
    decision_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_entry_outcomes (
    decision_id TEXT PRIMARY KEY REFERENCES prospective_entry_requests(decision_id),
    known_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS prospective_requests_no_update BEFORE UPDATE ON prospective_entry_requests
BEGIN SELECT RAISE(ABORT, 'prospective requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_requests_no_delete BEFORE DELETE ON prospective_entry_requests
BEGIN SELECT RAISE(ABORT, 'prospective requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_outcomes_no_update BEFORE UPDATE ON prospective_entry_outcomes
BEGIN SELECT RAISE(ABORT, 'prospective outcomes are immutable'); END;
CREATE TRIGGER IF NOT EXISTS prospective_outcomes_no_delete BEFORE DELETE ON prospective_entry_outcomes
BEGIN SELECT RAISE(ABORT, 'prospective outcomes are immutable'); END;
